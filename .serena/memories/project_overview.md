# SignalPy Microkernel + Prismi3 Backend

Two codebases in one repo:

## SignalPy Kernel (src/signalpy/)
- Signal-based reactive component kernel for Python backend services
- 12 decorators, ~2600 LOC, zero deps
- Tests: `PYTHONPATH=src python3 -m pytest src/signalpy/tests/ -q`
- Docs: `quarto render docs`

## Prismi3 Backend (prismi3-backend/)
- Copy of work-prismi3-agent/src/prismi3 for redesign analysis
- Read-only reference — do not modify source repo
- 161 Python files, multi-layer agent platform

## Commands
- Test: `PYTHONPATH=src python3 -m pytest src/signalpy/tests/ -q`
- Build: `python3 -m build`
- Render docs: `quarto render docs`
- Git: standard git on Darwin
