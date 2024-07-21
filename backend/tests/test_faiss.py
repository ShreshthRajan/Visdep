# test_faiss_import.py
try:
    import faiss
    print("Faiss imported successfully!")
except ImportError as e:
    print(f"Error importing faiss: {e}")
