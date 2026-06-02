# app/collectors/__init__.py
from app.collectors.mrv_collector import MRVCollector
from app.collectors.direcional_collector import DirecionalCollector
from app.collectors.cury_collector import CuryCollector

ALL_COLLECTORS = [MRVCollector, DirecionalCollector, CuryCollector]
