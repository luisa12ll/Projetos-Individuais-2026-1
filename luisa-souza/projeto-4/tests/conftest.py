# tests/__init__.py
# tests/conftest.py — Configuração global dos testes
import os

# Garante que os testes usam banco em memória
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GEMINI_API_KEY", "test-key-placeholder")
os.environ.setdefault("PDF_STORAGE_DIR", "/tmp/uda_test_pdfs")
