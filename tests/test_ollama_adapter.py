import asyncio
import io
import json
from datetime import date
from urllib.error import URLError

import pytest
from coalition_travel.application.request_understanding import (
    RequestInputError,
    RequestProviderError,
    StructuredOutputError,
    understand_request,
)
from coalition_travel.domain.request import TravelRequestDraft
from coalition_travel.infrastructure.llm.ollama import (
    LLMProviderError,
    OllamaStructuredRequestExtractor,
    transport_schema,
)
from evaluate_requests import (
    DEFAULT_DATASET,
    evaluate,
    load_dataset,
    load_profile_dataset,
)
from pydantic import ValidationError


def _http_response(content):
    payload = {"message": {"role": "assistant", "content": content}}
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_ollama_adapter_sends_json_schema_and_validates_response(monkeypatch):
    received = {}
    output = json.dumps(
        {
            "destination": "Tokyo",
            "travellers": 2,
            "budget_per_person": "500.00",
            "currency": "EUR",
            "departure_after": None,
            "arrival_before": "2027-02-20",
            "direct_flight": "preferred",
            "excluded_suppliers": [],
        }
    )

    def fake_urlopen(request, timeout):
        received["url"] = request.full_url
        received["body"] = json.loads(request.data)
        received["timeout"] = timeout
        return _http_response(output)

    monkeypatch.setattr("coalition_travel.infrastructure.llm.ollama.urlopen", fake_urlopen)
    extractor = OllamaStructuredRequestExtractor("qwen-local", timeout_seconds=12)
    reference_date = date(2026, 11, 18)

    result = asyncio.run(extractor.extract("Two people to Tokyo", reference_date))

    assert isinstance(result, TravelRequestDraft)
    assert result.destination == "Tokyo"
    assert result.arrival_before == date(2027, 2, 20)
    assert received["url"] == "http://localhost:11434/api/chat"
    assert received["body"]["format"] == transport_schema()  # final mission: all keys required
    assert received["body"]["options"]["temperature"] == 0
    assert received["body"]["stream"] is False
    assert reference_date.isoformat() in received["body"]["messages"][1]["content"]
    assert received["timeout"] == 12


def test_ollama_adapter_records_and_sends_reproducibility_parameters(monkeypatch):
    received = {}
    output = json.dumps({"destination": "Tokyo", "travellers": 1, "budget_per_person": "500"})

    def fake_urlopen(request, timeout):
        received["body"] = json.loads(request.data)
        return _http_response(output)

    monkeypatch.setattr("coalition_travel.infrastructure.llm.ollama.urlopen", fake_urlopen)
    extractor = OllamaStructuredRequestExtractor("qwen-local", temperature=0.15, seed=71)

    asyncio.run(extractor.extract("One person to Tokyo, 500 EUR", date(2026, 1, 1)))

    assert extractor.prompt_version == "travel-request-extraction-v2"  # I4, D-I4-12
    assert extractor.inference_parameters == {"temperature": 0.15, "stream": False, "seed": 71}
    assert received["body"]["options"] == {"temperature": 0.15, "seed": 71}


def test_ollama_adapter_includes_retrieved_context_with_source_references(monkeypatch):
    received = {}
    output = json.dumps(
        {
            "destination": "Tokyo",
            "travellers": 1,
            "budget_per_person": "500",
            "currency": "EUR",
            "direct_flight": "any",
            "excluded_suppliers": [],
        }
    )

    def fake_urlopen(request, timeout):
        received["body"] = json.loads(request.data)
        return _http_response(output)

    monkeypatch.setattr("coalition_travel.infrastructure.llm.ollama.urlopen", fake_urlopen)
    extractor = OllamaStructuredRequestExtractor("qwen-local")
    context = "[source=policy.md; document_id=policy]\nPolicy passage"

    result = asyncio.run(extractor.extract_with_context("Tokyo", date(2026, 1, 1), context))

    assert isinstance(result, TravelRequestDraft)
    user_prompt = received["body"]["messages"][1]["content"]
    assert "<knowledge_context>" in user_prompt
    assert "source=policy.md" in user_prompt
    assert "</knowledge_context>" in user_prompt


def test_end_to_end_request_understanding_returns_validated_result_and_provider_metrics(
    monkeypatch,
):
    output = json.dumps(
        {
            "destination": "Tokyo",
            "travellers": 2,
            "budget_per_person": "500.00",
            "currency": "EUR",
            "direct_flight": "any",
            "excluded_suppliers": [],
        }
    )
    monkeypatch.setattr(
        "coalition_travel.infrastructure.llm.ollama.urlopen",
        lambda request, timeout: _http_response(output),
    )
    extractor = OllamaStructuredRequestExtractor("qwen-local")

    result = asyncio.run(
        understand_request("Two people to Tokyo, max 500 EUR each", extractor, date(2026, 1, 1))
    )

    assert result.status == "ready"
    assert result.provider == "ollama"
    assert result.model == "qwen-local"
    assert result.latency_ms >= 0


def test_synthetic_evaluation_dataset_has_valid_annotated_records():
    records = load_dataset(DEFAULT_DATASET)

    assert len(records) == 26
    assert len({record["id"] for record in records}) == len(records)
    assert all(isinstance(record["expected"], TravelRequestDraft) for record in records)


def test_profile_dataset_is_versioned_and_profiles_are_scored_without_ids_or_order():
    records = load_profile_dataset(DEFAULT_DATASET.parent / "request_profiles_v1.jsonl")

    assert len(records) == 7
    assert records[0]["expected"].profiles[0].traveller_count == 2


def test_evaluation_reports_provider_failures_and_attempt_latency():
    class FailingExtractor:
        provider_name = "fake"
        model = "offline"

        async def extract(self, text, reference_date):
            raise LLMProviderError("offline")

    result = asyncio.run(evaluate(load_dataset(DEFAULT_DATASET)[:1], FailingExtractor()))

    assert result["successful_calls"] == 0
    assert result["failed_calls"] == 1
    assert result["mean_latency_ms"] is not None
    assert result["errors"] == [{"id": "fr-basic", "error": "LLMProviderError"}]
    assert result["examples"][0]["actual_status"] == "extraction_error"
    assert "status_confusion_matrix" in result


def test_evaluation_continues_after_typed_extraction_error():
    records = load_dataset(DEFAULT_DATASET)[:2]

    class IntermittentExtractor:
        provider_name = "fake"
        model = "offline"

        async def extract(self, text, reference_date):
            if text == records[0]["text"]:
                raise StructuredOutputError("bad model output")
            return records[1]["expected"]

    result = asyncio.run(evaluate(records, IntermittentExtractor()))

    assert result["successful_calls"] == 1
    assert result["failed_calls"] == 1
    assert result["samples"] == 2
    assert result["errors"] == [{"id": records[0]["id"], "error": "StructuredOutputError"}]


def test_evaluation_counts_oversized_request_and_continues_without_network():
    records = load_dataset(DEFAULT_DATASET)[:1]
    records[0]["text"] = "A request that is too long"
    extractor = OllamaStructuredRequestExtractor("qwen-local", max_input_chars=5)

    result = asyncio.run(evaluate(records, extractor))

    assert result["successful_calls"] == 0
    assert result["failed_calls"] == 1
    assert result["errors"] == [{"id": records[0]["id"], "error": "RequestInputError"}]


def test_evaluation_does_not_swallow_unclassified_value_error():
    class BuggyExtractor:
        provider_name = "fake"
        model = "buggy"

        async def extract(self, text, reference_date):
            raise ValueError("unexpected programming error")

    records = load_dataset(DEFAULT_DATASET)[:1]

    with pytest.raises(ValueError, match="unexpected programming error"):
        asyncio.run(evaluate(records, BuggyExtractor()))


def test_evaluation_does_not_swallow_raw_pydantic_validation_error():
    class NonconformingExtractor:
        provider_name = "fake"
        model = "nonconforming"

        async def extract(self, text, reference_date):
            TravelRequestDraft.model_validate({"destination": "Tokyo", "travellers": 0})

    records = load_dataset(DEFAULT_DATASET)[:1]

    with pytest.raises(ValidationError):
        asyncio.run(evaluate(records, NonconformingExtractor()))


def test_ollama_adapter_reports_transport_errors_without_hiding_them(monkeypatch):
    def failed_request(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr("coalition_travel.infrastructure.llm.ollama.urlopen", failed_request)
    extractor = OllamaStructuredRequestExtractor("qwen-local")

    with pytest.raises(LLMProviderError, match="Ollama request failed"):
        asyncio.run(extractor.extract("Tokyo", date(2026, 1, 1)))


def test_ollama_adapter_keeps_schema_failures_distinct(monkeypatch):
    monkeypatch.setattr(
        "coalition_travel.infrastructure.llm.ollama.urlopen",
        lambda request, timeout: _http_response('{"destination": "Tokyo", "travellers": 0}'),
    )
    extractor = OllamaStructuredRequestExtractor("qwen-local")

    with pytest.raises(StructuredOutputError) as error:
        asyncio.run(extractor.extract("Tokyo", date(2026, 1, 1)))
    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize("content", ["{not valid json", '{"destination":"Tokyo","travellers":0}'])
def test_request_understanding_propagates_nonconforming_llm_output_as_technical_error(
    monkeypatch, content
):
    monkeypatch.setattr(
        "coalition_travel.infrastructure.llm.ollama.urlopen",
        lambda request, timeout: _http_response(content),
    )
    extractor = OllamaStructuredRequestExtractor("qwen-local")

    with pytest.raises(StructuredOutputError):
        asyncio.run(understand_request("A valid travel request", extractor, date(2026, 1, 1)))


def test_provider_error_uses_application_error_contract(monkeypatch):
    def failed_request(request, timeout):
        raise URLError("offline")

    monkeypatch.setattr("coalition_travel.infrastructure.llm.ollama.urlopen", failed_request)
    extractor = OllamaStructuredRequestExtractor("qwen-local")

    with pytest.raises(RequestProviderError):
        asyncio.run(understand_request("Tokyo", extractor, date(2026, 1, 1)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model": ""},
        {"model": "test", "base_url": "localhost:11434"},
        {"model": "test", "timeout_seconds": 0},
        {"model": "test", "max_input_chars": 0},
    ],
)
def test_ollama_adapter_rejects_invalid_configuration(kwargs):
    with pytest.raises((TypeError, ValueError)):
        OllamaStructuredRequestExtractor(**kwargs)


def test_ollama_adapter_limits_input_size():
    extractor = OllamaStructuredRequestExtractor("qwen-local", max_input_chars=5)

    with pytest.raises(RequestInputError, match="exceeds"):
        asyncio.run(extractor.extract("six chars", date(2026, 1, 1)))


def test_the_transport_schema_requires_every_key_and_changes_nothing_else():
    """Final mission: without required keys, constrained decoding let models omit fields."""
    pydantic_schema = TravelRequestDraft.model_json_schema()
    sent = transport_schema()
    assert sent["required"] == list(sent["properties"])
    for name, node in sent["$defs"].items():
        if node.get("type") == "object":
            assert node["required"] == list(node["properties"]), name

    def without_required(schema):
        stripped = {key: value for key, value in schema.items() if key != "required"}
        stripped["$defs"] = {
            name: {key: value for key, value in node.items() if key != "required"}
            for name, node in schema["$defs"].items()
        }
        return stripped

    assert without_required(sent) == without_required(pydantic_schema)
    assert "required" not in pydantic_schema  # the Pydantic model itself is unchanged
    for name, node in pydantic_schema["$defs"].items():  # existing requirements are kept
        assert set(node.get("required", ())) <= set(sent["$defs"][name]["required"])
