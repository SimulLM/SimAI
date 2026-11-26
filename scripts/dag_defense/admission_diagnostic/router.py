"""Opt-in wrapper; local diagnostic only."""
import importlib.util,pathlib
from middleware import AdmissionFence
p=pathlib.Path(__file__).resolve().parents[3]/'docs/dag_defense/environment/scripts/pd_stream_proxy.py'
s=importlib.util.spec_from_file_location('diagnostic_pd_stream_proxy',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);app=AdmissionFence(m.app)
