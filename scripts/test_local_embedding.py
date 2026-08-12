import time

from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EXPECTED_DIMENSIONS = 384


print(f"Loading model: {MODEL_NAME}")

start = time.perf_counter()

model = SentenceTransformer(
    MODEL_NAME,
    device="cpu",
)

load_time = time.perf_counter() - start

print(f"Model loaded in {load_time:.2f}s")


text = (
    "SKU GRC-001 is Fruit 1 in the Fruit category of Grocery Retail. "
    "It is perishable, branded Brava, and associated with vendor "
    "Everest Wholesale."
)

start = time.perf_counter()

embedding = model.encode(
    text,
    normalize_embeddings=True,
)

embed_time = time.perf_counter() - start


print()
print(f"Dimensions : {len(embedding)}")
print(f"Embed time : {embed_time:.4f}s")
print(f"First 5    : {embedding[:5]}")


if len(embedding) != EXPECTED_DIMENSIONS:
    raise RuntimeError(
        f"Expected {EXPECTED_DIMENSIONS} dimensions, "
        f"got {len(embedding)}"
    )


print()
print("[PASS] Local BGE embedding works.")