"""Readable terminal presentation of a proposal (specification §9.1, scope review §7.1).

The renderer reads a ``TripProposal`` only, never an internal object of the engine. The
text follows the canonical order of the JSON and contains no timestamp other than the
reference date, so it is identical byte for byte for an identical proposal. The
validated-request summary and the status messages are built from validated fields only;
the raw text typed by the person is never copied (B9).
"""

from collections.abc import Mapping
from decimal import Decimal

from coalition_travel.application.request_contracts import TravelRequestDraft, draft_document
from coalition_travel.application.trip_proposal import (
    JournalView,
    TripProposal,
)
from coalition_travel.infrastructure.presentation.explanations_fr import (
    REQUEST_REJECTION_MESSAGES,
    euros,
    euros_exact,
    explanation_message,
    forbidden_term_message,
    needs_clarification_message,
    unknown_place_message,
    violation_text,
)
from coalition_travel.infrastructure.presentation.json_renderer import ensure_vocabulary

FORBIDDEN_TERM_PREFIX = "forbidden_term: "

STATUS_LABELS = {
    "served_in_coalition": "demande servie dans une coalition",
    "alone_no_beneficial_coalition": "demande traitée seule",
    "alone_social_optimum": "demande traitée seule",
    "no_admissible_offer": "aucune offre admissible",
    "no_solo_reference": "aucun prix de référence",
    "component_too_large": "groupe de demandes trop grand pour le calcul",
    "capacity_model_violated": "capacité des offres dépassée",
}
DIRECT_LABELS = {"any": "indifférent", "preferred": "préféré", "required": "exigé"}
ACTOR_LABELS = {"seller": "vendeur", "leader": "mandataire du groupe"}
TYPE_LABELS = {"PROPOSE": "propose", "ACCEPT": "accepte", "REJECT": "refuse"}
NEGOTIATION_STATUS_LABELS = {
    "agreement": "accord",
    "rejected": "sans accord (refus)",
    "turn_limit": "sans accord (limite de tours)",
}
TERMINAL_REASON_LABELS = {
    "leader_counteroffers_exhausted": "contre-propositions du mandataire épuisées",
    "seller_rejected": "refus du vendeur",
    "router_iteration_limit": "limite de tours atteinte",
}
EXTRACTION_LABELS = {
    "draft-json": "brouillon JSON fourni",
    "llm": "modèle de langage local",
    "replay": "rejeu enregistré (test et démonstration)",
}


def _decimal_euros(value) -> str:
    amount = Decimal(str(value))
    cents = amount * 100
    if cents == cents.to_integral_value():
        return euros(int(cents))
    return f"{str(amount).replace('.', ',')} €"


def _date(value) -> str:
    return "non précisée" if value is None else str(value)


def _suppliers(values) -> str:
    return ", ".join(values) if values else "aucun"


TRIP_TYPE_LABELS = {"one_way": "aller simple", "round_trip": "aller-retour"}


def _window(after, before) -> str:
    if after is None and before is None:
        return "non précisée"
    if after == before:
        return f"le {after}"
    return f"entre le {_date(after)} et le {_date(before)}"


def _route_request_lines(draft: Mapping) -> list[str]:
    """Summary of a v2 request (I4): the route, then the v1 fields that keep a meaning."""
    trip_type = draft["trip_type"]
    lines = [
        f"- départ de : {draft['origin']}",
        f"- destination : {draft['destination']}",
        f"- type de trajet : {TRIP_TYPE_LABELS.get(trip_type, 'non précisé')}",
        f"- voyageurs : {draft['travellers']}",
        f"- budget par personne : {_decimal_euros(draft['budget_per_person'])}",
        f"- départ de l'aller : {_window(draft['departure_after'], draft['departure_before'])}",
    ]
    if trip_type != "one_way":
        lines.append(
            f"- départ du retour : {_window(draft['return_after'], draft['return_before'])}"
        )
    lines += [
        f"- arrivée de l'aller au plus tard : {_date(draft['arrival_before'])}",
        f"- vol direct : {DIRECT_LABELS[draft['direct_flight']]}",
        f"- fournisseurs exclus : {_suppliers(draft['excluded_suppliers'])}",
    ]
    for profile in draft["profiles"]:
        details = [f"{profile['traveller_count']} voyageur(s)"]
        if profile["budget_per_person"] is not None:
            details.append(f"budget {_decimal_euros(profile['budget_per_person'])}")
        if profile["departure_after"] is not None or profile["departure_before"] is not None:
            window = _window(profile["departure_after"], profile["departure_before"])
            details.append(f"départ de l'aller {window}")
        if profile["return_after"] is not None or profile["return_before"] is not None:
            details.append(
                f"départ du retour {_window(profile['return_after'], profile['return_before'])}"
            )
        if profile["direct_flight"] is not None:
            details.append(f"vol direct {DIRECT_LABELS[profile['direct_flight']]}")
        if profile["excluded_suppliers"]:
            details.append(f"fournisseurs exclus {_suppliers(profile['excluded_suppliers'])}")
        lines.append(f"- profil {profile['profile_id']} : " + ", ".join(details))
    return lines


def _request_lines(draft: Mapping) -> list[str]:
    if "origin" in draft:  # v2: draft_document shows the route keys of a route request only
        return _route_request_lines(draft)
    lines = [
        f"- destination : {draft['destination']}",
        f"- voyageurs : {draft['travellers']}",
        f"- budget par personne : {_decimal_euros(draft['budget_per_person'])}",
        f"- départ au plus tôt : {_date(draft['departure_after'])}",
        f"- arrivée au plus tard : {_date(draft['arrival_before'])}",
        f"- vol direct : {DIRECT_LABELS[draft['direct_flight']]}",
        f"- fournisseurs exclus : {_suppliers(draft['excluded_suppliers'])}",
        "- ville de départ : non prise en compte dans cette version",
    ]
    for profile in draft["profiles"]:
        details = [f"{profile['traveller_count']} voyageur(s)"]
        if profile["budget_per_person"] is not None:
            details.append(f"budget {_decimal_euros(profile['budget_per_person'])}")
        if profile["departure_after"] is not None:
            details.append(f"départ au plus tôt {profile['departure_after']}")
        if profile["arrival_before"] is not None:
            details.append(f"arrivée au plus tard {profile['arrival_before']}")
        if profile["direct_flight"] is not None:
            details.append(f"vol direct {DIRECT_LABELS[profile['direct_flight']]}")
        if profile["excluded_suppliers"]:
            details.append(f"fournisseurs exclus {_suppliers(profile['excluded_suppliers'])}")
        lines.append(f"- profil {profile['profile_id']} : " + ", ".join(details))
    return lines


def render_request_summary(draft: TravelRequestDraft) -> str:
    """Summary of the understood request, shown before the validation question."""
    if not isinstance(draft, TravelRequestDraft):
        raise TypeError("draft must be a TravelRequestDraft")
    lines = ["Demande comprise :", *_request_lines(draft_document(draft))]
    return ensure_vocabulary("\n".join(lines) + "\n")


# --- proposal -----------------------------------------------------------------------------


def _offer_lines(proposal: TripProposal) -> list[str]:
    lines = []
    for offer in proposal.offers:
        kind = "vol direct" if offer.direct else "avec escale"
        if offer.origin is not None:  # v2 package (I4)
            lines.append(
                f"- {offer.offer_id} : {offer.supplier_id}, {offer.origin} → {offer.destination}, "
                f"{TRIP_TYPE_LABELS[offer.trip_type]}, {kind}, capacité {offer.capacity_seats} "
                "places"
            )
            for title, leg in (("aller", offer.outbound), ("retour", offer.return_leg)):
                if leg is not None:
                    leg_kind = "vol direct" if leg.direct else "avec escale"
                    lines.append(
                        f"  {title} : départ {leg.departure_date}, arrivée {leg.arrival_date}, "
                        f"{leg_kind}, vol {leg.leg_ref}, {leg.capacity_seats} places"
                    )
        else:
            lines.append(
                f"- {offer.offer_id} : {offer.supplier_id}, {offer.destination}, départ "
                f"{offer.departure_date}, arrivée {offer.arrival_date}, {kind}, capacité "
                f"{offer.capacity_seats} places"
            )
        tiers = " ; ".join(
            f"dès {tier.min_seats} place(s) : {euros(tier.list_per_seat_cents)} par place"
            for tier in offer.tiers
        )
        lines.append(f"  prix catalogue : {tiers}")
        if offer.admissible:
            lines.append("  admissible pour votre demande")
        else:
            reasons = " ; ".join(violation_text(v) for v in offer.violations)
            lines.append(f"  écartée : {reasons}")
        for note in offer.notes:
            if note.code == "direct_preference_not_met":
                lines.append(
                    f"  note : préférence pour un vol direct non satisfaite (profil "
                    f"{note.profile_id})"
                )
    return lines


def _journal_lines(journal: JournalView, indent: str) -> list[str]:
    status = NEGOTIATION_STATUS_LABELS.get(journal.status, journal.status)
    head = (
        f"{indent}{journal.quantity_seats} place(s), palier dès "
        f"{journal.price_tier_min_seats} place(s), prix catalogue "
        f"{euros(journal.catalog_total_cents)} ; {status} en {journal.turns} tour(s)"
    )
    if journal.agreed_total_cents is not None:
        head += f", prix négocié (simulation) {euros(journal.agreed_total_cents)}"
    if journal.terminal_reason is not None:
        head += f" ({TERMINAL_REASON_LABELS.get(journal.terminal_reason, journal.terminal_reason)})"
    lines = [head]
    if journal.leader_initial_total_cents is not None:
        lines.append(
            f"{indent}première offre du mandataire : {euros(journal.leader_initial_total_cents)}"
        )
    for message in journal.messages:
        actor = ACTOR_LABELS.get(message.actor, message.actor)
        verb = TYPE_LABELS.get(message.type, message.type)
        if message.total_cents is not None:
            amount = euros(message.total_cents)
        elif message.actor == "leader" and journal.leader_initial_total_cents is None:
            amount = "montant non publié"
        else:
            amount = "sans montant"
        lines.append(f"{indent}{message.index}. {actor} {verb} : {amount}")
    return lines


def _solo_lines(proposal: TripProposal) -> list[str]:
    solo = proposal.solo
    if solo is None:
        return ["Aucune négociation : la capacité des offres est dépassée."]
    if solo.status == "no_admissible_offer":
        return ["Aucune négociation : aucune offre admissible."]
    lines = []
    if solo.status == "referenced":
        lines.append(
            f"Prix de référence de votre demande : {euros(solo.agreed_total_cents)} "
            f"(offre {solo.offer_id}, prix négocié (simulation))"
        )
    else:
        lines.append("Aucune négociation individuelle n'a abouti.")
    for attempt in solo.attempts:
        lines.append(f"- offre {attempt.offer_id} :")
        lines.extend(_journal_lines(attempt.journal, "  "))
    return lines


def _block_lines(proposal: TripProposal) -> list[str]:
    block = proposal.block
    lines = [
        f"Offre commune : {block.offer_id}",
        f"Places : {block.seats} (palier dès {block.price_tier_min_seats} place(s))",
        f"Prix catalogue : {euros(block.catalog_total_cents)}",
        f"Prix négocié (simulation) : {euros(block.cost_cents)}",
        f"Somme des prix de référence : {euros(block.reference_total_cents)}",
        f"Valeur créée (économie collective) : {euros(block.value_cents)}",
        "Membres :",
    ]
    for member in block.members:
        places = f"{member.seats} place(s)"
        lines.append(f"- {member.label} : {places}, paiement {euros(member.payment_cents)}")
    if block.negotiation is not None:
        lines.append("Négociation du groupe (montants du mandataire non publiés) :")
        lines.extend(_journal_lines(block.negotiation, "  "))
    return lines


def _allocation_lines(proposal: TripProposal) -> list[str]:
    allocation = proposal.allocation
    return [
        f"Prix de référence de votre demande : {euros(allocation.reference_cents)}",
        f"Contribution à la valeur créée (Shapley) : {euros_exact(allocation.phi_cents)}",
        f"Économie après ajustement : {euros_exact(allocation.y_cents)}",
        f"Économie de votre demande : {euros(allocation.saving_cents)}",
        f"Paiement de votre demande : {euros(allocation.payment_cents)}",
    ]


def _traveller_lines(proposal: TripProposal) -> list[str]:
    lines = []
    for traveller in proposal.travellers:
        line = (
            f"- profil {traveller.profile_id}, place {traveller.seat_rank} : "
            f"{euros(traveller.amount_cents)} (budget {euros(traveller.budget_cents)})"
        )
        if traveller.profile_saturated:
            line += ", budget atteint"
        lines.append(line)
    return lines


def _provenance_lines(proposal: TripProposal) -> list[str]:
    provenance = proposal.provenance
    extraction = provenance.extraction
    source = EXTRACTION_LABELS[extraction.source]
    if extraction.model is not None:
        source += f" ({extraction.provider}, {extraction.model})"
    return [
        f"- date de référence : {provenance.reference_date}",
        f"- catalogue : {provenance.catalog_version}",
        f"- carnet de demandes : {provenance.pool_version or 'aucun'}",
        f"- planification : {provenance.planning_version}",
        f"- formation : {provenance.formation_adapter_version} ({provenance.formation_method})",
        f"- allocation : {provenance.allocation_version} (θ = {provenance.theta_cents})",
        f"- extraction de la demande : {source}",
    ]


def render_proposal_text(proposal: TripProposal) -> str:
    """The proposal as readable text; accepts a TripProposal only."""
    if type(proposal) is not TripProposal:
        raise TypeError("the text renderer accepts a TripProposal only")
    status = proposal.explanations[0]
    sections = [
        [proposal.simulation.notice, f"Date de référence : {proposal.provenance.reference_date}"],
        ["== Demande validée ==", *_request_lines(proposal.request.draft)],
        [
            "== Résultat ==",
            f"Statut : {STATUS_LABELS[proposal.status.code]}",
            explanation_message(status),
        ],
        ["== Offres du catalogue ==", *_offer_lines(proposal)],
        ["== Négociations individuelles (simulation) ==", *_solo_lines(proposal)],
    ]
    if proposal.block is not None:
        title = "== Groupe constitué ==" if len(proposal.block.members) > 1 else "== Votre bloc =="
        sections.append([title, *_block_lines(proposal)])
        sections.append(["== Répartition calculée ==", *_allocation_lines(proposal)])
        sections.append(["== Paiements par voyageur ==", *_traveller_lines(proposal)])
    others = list(proposal.explanations[1:])
    if others:
        sections.append(
            ["== Explications ==", *(f"- {explanation_message(item)}" for item in others)]
        )
    sections.append(["== Provenance ==", *_provenance_lines(proposal)])
    text = "\n\n".join("\n".join(section) for section in sections) + "\n"
    return ensure_vocabulary(text)


# --- status messages (standard error) -----------------------------------------------------


def _invalid_text(errors) -> str:
    lines = ["Demande invalide (détail technique) :"]
    for error in errors:
        if error.startswith(FORBIDDEN_TERM_PREFIX):
            lines.append(f"- {forbidden_term_message(error[len(FORBIDDEN_TERM_PREFIX) :])}")
        else:
            lines.append(f"- {error}")
    return "\n".join(lines)


def render_status_text(document: Mapping) -> str:
    """Message for a request without proposal (exit codes 2, 3 and 4)."""
    status = document["status"]
    if status == "needs_clarification":
        text = "Clarification requise. " + needs_clarification_message(document["missing_fields"])
    elif status == "unknown_place":  # v2 (I4)
        text = "Clarification requise. " + unknown_place_message(
            document["fields"], document["known_places"]
        )
    elif status == "invalid":
        text = _invalid_text(document["errors"])
    elif status == "request_rejected":
        reason = document["reason"]
        if reason in REQUEST_REJECTION_MESSAGES:
            text = "Demande non retenue. " + REQUEST_REJECTION_MESSAGES[reason]
        elif document["rejection_status"] == "needs_clarification":
            text = "Clarification requise. " + needs_clarification_message(
                document["missing_fields"]
            )
        else:
            text = _invalid_text(document["errors"])
    else:
        text = "Demande non validée : aucune simulation n'a été lancée."
    return ensure_vocabulary(text + "\n")
