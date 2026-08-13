import time
import numpy as np

from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EXPECTED_DIMENSIONS = 384

# BGE's recommended retrieval instruction for short queries.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def main():
    print("=" * 70)
    print("Local BGE Embedding Test")
    print("=" * 70)

    print(f"\nLoading model: {MODEL_NAME}")
    start = time.perf_counter()

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )

    load_seconds = time.perf_counter() - start

    print(f"Model loaded in : {load_seconds:.2f}s")
    print(f"Device          : {model.device}")

    # --------------------------------------------------------------
    # Document embedding
    # --------------------------------------------------------------

    document = (
        "SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail. "
        "It is perishable, branded Brava, with main vendor Everest Wholesale. "
        "It sells in Bottle and is purchased in Crate with pack factor 12."
    )

    start = time.perf_counter()

    document_embedding = model.encode(
        document,
        normalize_embeddings=True,
    )

    embed_seconds = time.perf_counter() - start

    print("\nDocument embedding")
    print("------------------")
    print(f"Dimensions      : {len(document_embedding)}")
    print(f"Embedding time  : {embed_seconds:.4f}s")
    print(f"Vector norm     : {np.linalg.norm(document_embedding):.6f}")
    print(f"First 5 values  : {document_embedding[:5]}")

    if len(document_embedding) != EXPECTED_DIMENSIONS:
        raise RuntimeError(
            f"Expected {EXPECTED_DIMENSIONS} dimensions, "
            f"got {len(document_embedding)}"
        )

    # --------------------------------------------------------------
    # Small semantic retrieval test
    # --------------------------------------------------------------

    documents = [
        (
            "SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail. "
            "It is a perishable product supplied by Everest Wholesale."
        ),
        (
            "Vendor V0001 is Aurora Supply Co. Commercial terms include "
            "Net 30 payment terms and FOB delivery terms."
        ),
        (
            "Reorder point is the inventory threshold used to determine "
            "when replenishment should be initiated."
        ),
    ]

    query = "Which document is about a perishable fruit product?"

    # BGE documents/passages do NOT need the retrieval instruction.
    doc_embeddings = model.encode(
        documents,
        normalize_embeddings=True,
    )

    # BGE recommends the instruction for short-query -> passage retrieval.
    query_embedding = model.encode(
        QUERY_PREFIX + query,
        normalize_embeddings=True,
    )

    # Since embeddings are normalized, dot product is equivalent
    # to cosine similarity.
    scores = doc_embeddings @ query_embedding

    ranked = sorted(
        enumerate(scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )

    print("\nSemantic retrieval test")
    print("-----------------------")
    print(f"Query: {query}\n")

    for rank, (index, score) in enumerate(ranked, start=1):
        print(f"{rank}. score={float(score):.4f}")
        print(f"   {documents[index]}")

    if ranked[0][0] != 0:
        raise RuntimeError(
            "Expected the Fruit/Grocery document to rank first."
        )

    print("\n[PASS] Local BGE embedding works.")
    print("[PASS] Vector dimension is 384.")
    print("[PASS] Normalized semantic retrieval works.")


if __name__ == "__main__":
    main()