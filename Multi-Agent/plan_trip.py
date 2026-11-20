"""coalition-travel-plan: one travel request to a simulated proposal (step I3-C).

Flow (scope review §6.2): options, reference date, catalogue v1 and demand pool v1, the
request (``--draft-json``, ``--prompt`` or interactive input, with at most three
clarification rounds), the vocabulary check of the person's strings (D-I3-17), the summary
of the understood request, the explicit validation (ID-10, unless ``--yes``), then
``plan_travel_request`` and the text or JSON output.

Streams: standard output receives only the final document (the proposal, or with
``--json`` the status document of §6.4); questions, summary and messages go to standard
error. Exit codes: 0 proposal, 1 technical error, 2 clarification needed, 3 invalid
request, 4 request not validated, 64 incorrect usage, 130 interruption.

Demonstration mode only (ID-1): the versioned catalogue v1 and demand pool v1.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from coalition_travel.application.request_contracts import (
    PROFILE_ROUTE_FIELDS,
    REQUEST_ROUTE_FIELDS,
    TravelRequestDraft,
    is_route_request,
)
from coalition_travel.application.request_understanding import (
    RequestInputError,
    understand_request,
    validate_request_draft,
)
from coalition_travel.application.travel_workflow import plan_travel_request
from coalition_travel.application.trip_proposal import (
    draft_json_extraction,
    llm_extraction,
    replay_extraction,
)
from coalition_travel.infrastructure.catalog.places import load_place_directory
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.llm.ollama import OllamaStructuredRequestExtractor
from coalition_travel.infrastructure.llm.replay import ReplayStructuredRequestExtractor
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.presentation.explanations_fr import (
    CLARIFICATION_QUESTIONS,
    unknown_place_message,
)
from coalition_travel.infrastructure.presentation.json_renderer import (
    STATUS_SCHEMA,
    STATUS_SCHEMA_V2,
    forbidden_term_error,
    invalid_document,
    needs_clarification_document,
    not_validated_document,
    reduce_validation_error,
    render_proposal_json,
    render_status_json,
    request_rejected_document,
    unknown_place_document,
)
from coalition_travel.infrastructure.presentation.text_renderer import (
    render_proposal_text,
    render_request_summary,
    render_status_text,
)
from coalition_travel.infrastructure.presentation.vocabulary import forbidden_user_fields
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog" / "catalog_v1.json"
POOL_PATH = ROOT / "data" / "demand" / "demand_pool_v1.jsonl"
# Route requests (I4, D-I4-2): catalogue v2, demand pool v2 and the place directory.
CATALOG_V2_PATH = ROOT / "data" / "catalog" / "catalog_v2.json"
POOL_V2_PATH = ROOT / "data" / "demand" / "demand_pool_v2.jsonl"
PLACES_PATH = ROOT / "data" / "catalog" / "places_v1.json"

EXIT_OK = 0
EXIT_TECHNICAL = 1
EXIT_CLARIFICATION = 2
EXIT_INVALID = 3
EXIT_NOT_VALIDATED = 4
EXIT_USAGE = 64  # sysexits EX_USAGE (D-I3-3)
EXIT_INTERRUPTED = 130

MAX_CLARIFICATION_ROUNDS = 3
ACCEPTED_ANSWERS = frozenset({"o", "oui"})
REQUEST_QUESTION = "Décrivez votre demande de voyage : "
VALIDATION_QUESTION = "Valider cette demande et lancer la simulation ? [o/N] "
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.])/(?:[^\s'\":/]+/)+[^\s'\":/]*")


class UsageError(Exception):
    """Incorrect use of the command: exit code 64, with a message in French."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        if message.startswith("unrecognized arguments"):
            raise UsageError("option inconnue.")
        if "expected one argument" in message:
            raise UsageError("une option attend une valeur.")
        raise UsageError("options incorrectes.")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="coalition-travel-plan",
        description=(
            "Proposition simulée pour une demande de voyage : catalogue et vendeurs fictifs, "
            "aucune réservation."
        ),
    )
    source = parser.add_argument_group("demande")
    source.add_argument("--prompt", metavar="TEXTE", help="demande en langage naturel")
    source.add_argument(
        "--draft-json", metavar="FICHIER", help="demande structurée (TravelRequestDraft)"
    )
    source.add_argument(
        "--extractor-replay",
        metavar="FICHIER",
        help="rejeu de brouillons enregistrés, à la place du modèle (test et démonstration)",
    )
    parser.add_argument(
        "--reference-date", metavar="AAAA-MM-JJ", help="date de référence (défaut : aujourd'hui)"
    )
    parser.add_argument("--yes", action="store_true", help="valider la demande sans question")
    parser.add_argument("--json", action="store_true", help="sortie JSON canonique")
    return parser


class _Command:
    def __init__(self, stdin, stdout, stderr, environ, open_market, load_pool, today):
        self.stdin, self.stdout, self.stderr = stdin, stdout, stderr
        self.environ, self.open_market, self.load_pool = environ, open_market, load_pool
        self.today = today
        self.paths: dict[str, str] = {}
        self.source = "draft-json"
        self.reference_date: date | None = None
        self.as_json = False
        self.route = False  # the version of the request (D-I4-1); decides the documents
        self._places = None

    # --- streams --------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.stderr.write(text if text.endswith("\n") else text + "\n")
        self.stderr.flush()

    def ask(self, question: str) -> str:
        self.stderr.write(question)
        self.stderr.flush()
        return self.stdin.readline()

    def sanitize(self, message: str) -> str:
        """No file path in any message (B10): known paths become names, others a mark."""
        for path, label in sorted(self.paths.items(), key=lambda item: -len(item[0])):
            message = message.replace(path, label)
        return _ABSOLUTE_PATH.sub("<chemin>", message)

    def remember(self, path, label: str) -> None:
        for variant in {str(path), str(Path(path).absolute()), str(Path(path).resolve())}:
            self.paths[variant] = label

    # --- steps ----------------------------------------------------------------------

    def parse(self, argv):
        args = build_parser().parse_args(argv)
        if args.prompt is not None and args.draft_json is not None:
            raise UsageError("--prompt et --draft-json ne peuvent pas être utilisées ensemble.")
        if args.extractor_replay is not None and args.draft_json is not None:
            raise UsageError("--extractor-replay ne s'utilise qu'avec --prompt ou la saisie.")
        if args.reference_date is None:
            self.reference_date = self.today()
        else:
            try:
                if not _ISO_DATE.fullmatch(args.reference_date):
                    raise ValueError
                self.reference_date = date.fromisoformat(args.reference_date)
            except ValueError:
                raise UsageError("la date de référence doit avoir la forme AAAA-MM-JJ.") from None
        self.as_json = args.json
        return args

    def read_inputs(self, args):
        """Input files are read with the options: an unreadable file is a usage error."""
        draft_bytes = extractor = None
        if args.draft_json is not None:
            self.remember(args.draft_json, "--draft-json")
            try:
                draft_bytes = Path(args.draft_json).read_bytes()
            except OSError:
                raise UsageError("Fichier de --draft-json introuvable ou illisible.") from None
            return draft_bytes, None
        if args.extractor_replay is not None:
            self.remember(args.extractor_replay, "--extractor-replay")
            self.source = "replay"
            try:
                extractor = ReplayStructuredRequestExtractor(args.extractor_replay)
            except OSError:
                raise UsageError(
                    "Fichier de --extractor-replay introuvable ou illisible."
                ) from None
            return None, extractor
        model = self.environ.get("OLLAMA_MODEL", "").strip()
        if not model:
            raise UsageError(
                "--prompt et la saisie demandent la variable OLLAMA_MODEL, "
                "ou l'option --extractor-replay."
            )
        self.source = "llm"
        base_url = self.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return None, OllamaStructuredRequestExtractor(model, base_url=base_url)

    def extraction(self, extractor):
        if self.source == "draft-json":
            return draft_json_extraction()
        if self.source == "replay":
            return replay_extraction()
        return llm_extraction(extractor.model)

    def common(self) -> dict:
        schema = STATUS_SCHEMA_V2 if self.route else STATUS_SCHEMA
        return {"source": self.source, "reference_date": self.reference_date, "schema": schema}

    @property
    def places(self):
        if self._places is None:
            self.remember(PLACES_PATH, PLACES_PATH.name)
            self._places = load_place_directory(PLACES_PATH)
        return self._places

    def resolve_places(self, draft):
        """D-I4-9: canonical names for a route request, or the unknown place fields."""
        unknown, names = [], {}
        for field in ("origin", "destination"):
            spelling = getattr(draft, field)
            if spelling is None:
                continue
            canonical = self.places.resolve(spelling)
            if canonical is None:
                unknown.append(field)
            else:
                names[field] = canonical
        if unknown:
            return None, tuple(unknown)
        return TravelRequestDraft.model_validate(draft.model_dump(mode="json") | names), ()

    def unknown_place(self, fields):
        return unknown_place_document(
            source=self.source,
            reference_date=self.reference_date,
            fields=fields,
            known_places=self.places.names,
        )

    def from_draft_json(self, draft_bytes):
        try:
            draft = TravelRequestDraft.model_validate_json(draft_bytes)
        except ValidationError as exc:
            self.route = _raw_is_route(draft_bytes)
            return invalid_document(errors=reduce_validation_error(exc), **self.common())
        self.route = is_route_request(draft)
        refused = self.refuse_forbidden_strings(draft)
        if refused is not None:
            return refused
        if self.route:
            resolved, unknown = self.resolve_places(draft)
            if unknown:
                return self.unknown_place(unknown)
            draft = resolved
        validation = validate_request_draft(draft, self.reference_date)
        if validation.status == "needs_clarification":
            return needs_clarification_document(
                missing_fields=validation.missing_fields, rounds=0, **self.common()
            )
        if validation.status == "invalid":
            return invalid_document(errors=validation.errors, **self.common())
        return draft

    def refuse_forbidden_strings(self, draft):
        """D-I3-17: before any display derived from the request, without rewriting it."""
        paths = forbidden_user_fields(draft)
        if not paths:
            return None
        return invalid_document(
            errors=[forbidden_term_error(path) for path in paths], **self.common()
        )

    def from_text(self, text, extractor):
        if text is None:
            text = self.ask(REQUEST_QUESTION).rstrip("\n")
        rounds = 0
        while True:
            try:
                result = asyncio.run(understand_request(text, extractor, self.reference_date))
            except RequestInputError as exc:
                return invalid_document(errors=[str(exc)], **self.common())
            request = result.request
            if request is not None:
                self.route = is_route_request(request)
                refused = self.refuse_forbidden_strings(request)
                if refused is not None:
                    return refused
            if request is not None and self.route:
                resolved, unknown = self.resolve_places(request)
                if unknown:  # a clarification round that lists the known places
                    if rounds == MAX_CLARIFICATION_ROUNDS:
                        return self.unknown_place(unknown)
                    message = unknown_place_message(unknown, self.places.names)
                    answer = self.ask(
                        f"Précision {rounds + 1}/{MAX_CLARIFICATION_ROUNDS} : {message} "
                    )
                    if answer == "":
                        return self.unknown_place(unknown)
                    text = text + "\n" + answer.rstrip("\n")
                    rounds += 1
                    continue
                request = resolved
            if result.status == "ready":
                return request
            if result.status == "invalid":
                return invalid_document(errors=result.errors, **self.common())
            missing = result.missing_fields
            if rounds == MAX_CLARIFICATION_ROUNDS:
                return needs_clarification_document(
                    missing_fields=missing, rounds=rounds, **self.common()
                )
            questions = " ".join(CLARIFICATION_QUESTIONS[field] for field in missing)
            answer = self.ask(f"Précision {rounds + 1}/{MAX_CLARIFICATION_ROUNDS} : {questions} ")
            if answer == "":  # end of input during a round
                return needs_clarification_document(
                    missing_fields=missing, rounds=rounds, **self.common()
                )
            text = text + "\n" + answer.rstrip("\n")
            rounds += 1

    def validated(self, yes: bool):
        """None when the person validates; otherwise the not_validated document."""
        if yes:
            return None
        answer = self.ask(VALIDATION_QUESTION)
        if answer == "":
            reason = "end_of_input"
        elif not answer.strip():
            reason = "empty_answer"
        elif answer.strip().casefold() in ACCEPTED_ANSWERS:
            return None
        else:
            reason = "refused"
        return not_validated_document(reason=reason, **self.common())

    def finish_with_status(self, document) -> int:
        text, code = render_status_json(document)  # validated before any writing
        self.say(render_status_text(document))
        if self.as_json:
            self.stdout.write(text)
            self.stdout.flush()
        return code

    def execute(self, argv) -> int:
        args = self.parse(argv)
        draft_bytes, extractor = self.read_inputs(args)
        if draft_bytes is not None:
            obtained = self.from_draft_json(draft_bytes)
        else:
            obtained = self.from_text(args.prompt, extractor)
        if not isinstance(obtained, TravelRequestDraft):
            return self.finish_with_status(obtained)
        draft = obtained
        # D-I4-2: the catalogue and the pool follow the version of the request.
        catalog_path = CATALOG_V2_PATH if self.route else CATALOG_PATH
        pool_path = POOL_V2_PATH if self.route else POOL_PATH
        self.remember(catalog_path, catalog_path.name)
        self.remember(pool_path, pool_path.name)
        market = self.open_market(catalog_path, self.reference_date)
        pool = self.load_pool(pool_path)
        self.say(render_request_summary(draft))
        refusal = self.validated(args.yes)
        if refusal is not None:
            return self.finish_with_status(refusal)
        self.say("Demande validée : simulation en cours.")
        result = plan_travel_request(
            draft,
            market=market,
            pool=pool,
            reference_date=self.reference_date,
            extraction=self.extraction(extractor),
        )
        if result.proposal is None:
            rejection = result.plan.rejections[0]
            return self.finish_with_status(
                request_rejected_document(rejection=rejection, **self.common())
            )
        if self.as_json:
            output = render_proposal_json(result.proposal)
        else:
            output = render_proposal_text(result.proposal)
        self.stdout.write(output)
        self.stdout.flush()
        return EXIT_OK


def _raw_is_route(raw: bytes) -> bool:
    """Version of a draft that failed validation, read from its JSON keys when possible."""
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    if any(name in document for name in REQUEST_ROUTE_FIELDS):
        return True
    profiles = document.get("profiles")
    return isinstance(profiles, list) and any(
        isinstance(profile, dict) and any(name in profile for name in PROFILE_ROUTE_FIELDS)
        for profile in profiles
    )


def run(
    argv,
    *,
    stdin=None,
    stdout=None,
    stderr=None,
    environ=None,
    open_market=open_simulated_market,
    load_pool=load_demand_pool,
    today=date.today,
) -> int:
    """Run the command and return its exit code; the streams can be replaced in tests."""
    command = _Command(
        stdin or sys.stdin,
        stdout or sys.stdout,
        stderr or sys.stderr,
        os.environ if environ is None else environ,
        open_market,
        load_pool,
        today,
    )
    try:
        return command.execute(argv)
    except KeyboardInterrupt:
        command.say("\nInterruption : aucune proposition n'a été produite.")
        return EXIT_INTERRUPTED
    except UsageError as exc:
        command.say(f"Usage incorrect : {exc}")
        command.say(build_parser().format_usage())
        return EXIT_USAGE
    except OSError as exc:
        command.say(f"Erreur technique : {type(exc).__name__}: {exc.strerror or 'erreur système'}")
        return EXIT_TECHNICAL
    except Exception as exc:  # noqa: BLE001 -- top level: any other failure is technical (code 1)
        command.say(f"Erreur technique : {type(exc).__name__}: {command.sanitize(str(exc))}")
        return EXIT_TECHNICAL


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
