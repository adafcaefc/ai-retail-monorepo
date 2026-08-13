import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EXPECTED_DIMENSIONS = 384
BATCH_SIZE = 16

ROOT_DIR = Path(__file__).resolve().parents[1]
CORPUS_FILE = ROOT_DIR / "generated" / "retail_documents.jsonl"


def percentile(values, p):
    return int(np.percentile(values, p))


def main():
    print("=" * 70)
    print("Retail 360 Local Embedding Benchmark")
    print("=" * 70)

    if not CORPUS_FILE.exists():
        raise FileNotFoundError(
            f"Corpus not found: {CORPUS_FILE}"
        )

    documents = []

    with CORPUS_FILE.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            obj = json.loads(line)

            documents.append(
                {
                    "doc_key": obj["doc_key"],
                    "doc_type": obj["doc_type"],
                    "retrieval_domain": obj["retrieval_domain"],
                    "content": obj["content"],
                }
            )

    print(f"\nDocuments loaded : {len(documents)}")

    # --------------------------------------------------------------
    # Load model
    # --------------------------------------------------------------

    print(f"Loading model    : {MODEL_NAME}")

    start = time.perf_counter()

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )

    model_load_seconds = time.perf_counter() - start

    print(f"Model load time  : {model_load_seconds:.2f}s")
    print(f"Device           : {model.device}")
    print(f"Max seq length   : {model.max_seq_length}")

    # --------------------------------------------------------------
    # Token analysis WITHOUT truncation
    # --------------------------------------------------------------

    print("\nAnalyzing token lengths...")

    tokenizer = model.tokenizer

    token_counts = []

    oversized = []

    for doc in documents:
        tokens = tokenizer(
            doc["content"],
            add_special_tokens=True,
            truncation=False,
        )

        count = len(tokens["input_ids"])
        token_counts.append(count)

        if count > model.max_seq_length:
            oversized.append(
                {
                    "doc_key": doc["doc_key"],
                    "doc_type": doc["doc_type"],
                    "retrieval_domain": doc["retrieval_domain"],
                    "tokens": count,
                }
            )

    print()
    print("Token distribution")
    print("------------------")
    print(f"Minimum   : {min(token_counts)}")
    print(f"Median    : {percentile(token_counts, 50)}")
    print(f"P90       : {percentile(token_counts, 90)}")
    print(f"P95       : {percentile(token_counts, 95)}")
    print(f"P99       : {percentile(token_counts, 99)}")
    print(f"Maximum   : {max(token_counts)}")

    print()
    print(
        f"Documents over {model.max_seq_length} tokens: "
        f"{len(oversized)}"
    )

    if oversized:
        print("\nOversized documents:")
        for doc in sorted(
            oversized,
            key=lambda x: x["tokens"],
            reverse=True,
        ):
            print(
                f"  {doc['tokens']:4d} tokens | "
                f"{doc['doc_type']:22s} | "
                f"{doc['doc_key']}"
            )

    # --------------------------------------------------------------
    # Embedding benchmark
    # --------------------------------------------------------------

    texts = [doc["content"] for doc in documents]

    print()
    print("Embedding corpus")
    print("----------------")
    print(f"Batch size : {BATCH_SIZE}")

    start = time.perf_counter()

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )

    elapsed = time.perf_counter() - start

    # --------------------------------------------------------------
    # Validation
    # --------------------------------------------------------------

    if embeddings.shape[0] != len(documents):
        raise RuntimeError(
            "Embedding count does not match document count."
        )

    if embeddings.shape[1] != EXPECTED_DIMENSIONS:
        raise RuntimeError(
            f"Expected {EXPECTED_DIMENSIONS} dimensions, "
            f"got {embeddings.shape[1]}"
        )

    norms = np.linalg.norm(embeddings, axis=1)

    if not np.allclose(norms, 1.0, atol=1e-4):
        raise RuntimeError(
            "One or more embeddings are not normalized."
        )

    docs_per_second = len(documents) / elapsed

    print()
    print("Benchmark results")
    print("-----------------")
    print(f"Documents       : {len(documents)}")
    print(f"Dimensions      : {embeddings.shape[1]}")
    print(f"Total time      : {elapsed:.2f}s")
    print(f"Documents/sec   : {docs_per_second:.2f}")
    print(f"Seconds/doc     : {elapsed / len(documents):.4f}")
    print(f"Vector shape    : {embeddings.shape}")
    print(
        f"Vector memory   : "
        f"{embeddings.nbytes / (1024 * 1024):.2f} MiB"
    )

    print()
    print("[PASS] Full corpus embedded successfully.")
    print("[PASS] All vectors are 384-dimensional.")
    print("[PASS] All vectors are normalized.")

    if oversized:
        print(
            "[WARN] Some source documents exceed the model sequence "
            "limit and require a chunking policy before Phase 5."
        )
    else:
        print(
            "[PASS] No semantic documents exceed the model "
            "sequence limit."
        )


if __name__ == "__main__":
    main()