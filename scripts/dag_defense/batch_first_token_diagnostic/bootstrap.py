"""Experimental DAG-only opt-in; never a pristine or frozen comparison."""
from patch import enable
enable()
from vidur.main import main
main()
