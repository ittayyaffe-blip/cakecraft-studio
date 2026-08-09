"""Dependency-free self-check for the pure logic in
`app.services.rag_service` — no network/DB/Anthropic API call required.
Run from `backend/`:

    python -m tests.test_rag_service

`retrieve()`'s real pgvector RPC and a real Claude call are still only
exercised live — see docs/BUSINESS_INTELLIGENCE_LAYER.md "Verification".
Everything below is offline: prompt construction, the embedding padding
logic, and — via the `answer_question_*` tests — the orchestration of
`answer_question()` itself, with `retrieve()` and the Anthropic client
mocked at their exact call boundary so the real `_build_prompt()` and
response-handling code still runs for real, just against fixed inputs.
"""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services import rag_service
from app.services.rag_service import EMBEDDING_DIMENSIONS, _build_prompt, embed_texts


def test_embed_texts_pads_to_fixed_dimension():
    # A tiny corpus has a vocabulary far smaller than EMBEDDING_DIMENSIONS
    # — this is exactly the real-world case that broke retrieval once
    # (see the migration that widened the column after this was caught
    # live): the vectorizer's raw output must always come back padded.
    vectorizer = TfidfVectorizer()
    vectorizer.fit(["chocolate cake recipe", "vanilla frosting guide"])
    vectors = embed_texts(vectorizer, ["a chocolate cake"])
    assert vectors.shape == (1, EMBEDDING_DIMENSIONS)


def test_embed_texts_matches_between_fit_and_transform_calls():
    # The single most important correctness property of the whole
    # retrieval pipeline: ingestion-time and query-time embeddings must
    # come out the same width from the same fitted vectorizer.
    vectorizer = TfidfVectorizer()
    corpus = ["wedding cake pricing and deposits", "allergen policy for nuts and dairy"]
    vectorizer.fit(corpus)
    ingestion_vectors = embed_texts(vectorizer, corpus)
    query_vector = embed_texts(vectorizer, ["what is the deposit policy"])
    assert ingestion_vectors.shape[1] == query_vector.shape[1] == EMBEDDING_DIMENSIONS


def test_embed_texts_no_padding_needed_when_vocabulary_is_large_enough():
    # Build a fake vectorizer-like object whose transform() already
    # returns exactly EMBEDDING_DIMENSIONS columns — padding should be a
    # no-op (zero columns added) rather than truncating or erroring.
    class _WideVectorizer:
        def transform(self, texts):
            class _Sparse:
                def toarray(self_inner):
                    return np.ones((len(texts), EMBEDDING_DIMENSIONS))

            return _Sparse()

    vectors = embed_texts(_WideVectorizer(), ["anything"])
    assert vectors.shape == (1, EMBEDDING_DIMENSIONS)
    assert (vectors == 1).all()  # unchanged, not zero-padded away


def test_build_prompt_includes_question_and_chunk_titles():
    chunks = [
        {"title": "Pricing Policy", "content": "Deposits are 30% for weddings."},
        {"title": "Wedding Cake Guide", "content": "Lead time is 14-45 days."},
    ]
    prompt = _build_prompt("What is the wedding deposit?", chunks)
    assert "What is the wedding deposit?" in prompt
    assert "Pricing Policy" in prompt
    assert "Deposits are 30% for weddings." in prompt
    assert "Wedding Cake Guide" in prompt


def test_build_prompt_instructs_grounding_in_provided_documents():
    prompt = _build_prompt("test question", [{"title": "X", "content": "Y"}])
    assert "ONLY" in prompt  # the actual RAG constraint: answer from context, not general knowledge


# --- answer_question() orchestration, mocked at the retrieve()/Claude ------
# boundary only. Everything in between (is_configured(), _build_prompt(),
# unpacking the response into {"answer", "sources"}) is the real code.


def test_answer_question_incorporates_retrieved_chunks_into_the_model_request():
    fake_chunks = [
        {
            "title": "Pricing Policy",
            "content": "Deposits are 30% for weddings.",
            "source_file": "pricing_policy.md",
            "similarity": 0.87,
        }
    ]
    fake_response = SimpleNamespace(content=[SimpleNamespace(type="text", text="Weddings require a 30% deposit.")])

    with (
        patch.object(rag_service, "retrieve", return_value=fake_chunks) as mock_retrieve,
        patch.object(rag_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(rag_service.anthropic, "Anthropic") as mock_anthropic_cls,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = fake_response
        result = rag_service.answer_question("What is the wedding deposit?")

    mock_retrieve.assert_called_once_with("What is the wedding deposit?", top_k=5)

    sent_prompt = mock_anthropic_cls.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Deposits are 30% for weddings." in sent_prompt  # retrieved content reached the model request
    assert "Pricing Policy" in sent_prompt
    assert "What is the wedding deposit?" in sent_prompt

    assert result["answer"] == "Weddings require a 30% deposit."  # mocked response handled correctly
    assert result["sources"] == [{"title": "Pricing Policy", "sourceFile": "pricing_policy.md", "similarity": 0.87}]


def test_answer_question_falls_back_cleanly_when_not_configured():
    fake_chunks = [
        {
            "title": "Allergen Policy",
            "content": "We label all nut-containing products.",
            "source_file": "allergen_policy.md",
            "similarity": 0.9,
        }
    ]
    with (
        patch.object(rag_service, "retrieve", return_value=fake_chunks),
        patch.object(rag_service.settings, "anthropic_api_key", None),
    ):
        result = rag_service.answer_question("Do you handle nut allergies?")

    assert "isn't available right now" in result["answer"]
    assert "Allergen Policy" in result["answer"]
    assert result["sources"][0]["title"] == "Allergen Policy"


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
