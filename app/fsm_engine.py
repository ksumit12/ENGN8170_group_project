#!/usr/bin/env python3
"""
FSM Engine interface and dynamic factory.

This module decouples the API/server from any concrete FSM implementation so the
core transition logic can be swapped without touching the rest of the system.

Default engine: app.entry_exit_fsm:EntryExitFSM
Override via env FSM_ENGINE="module_path:ClassName"
"""

import os
import importlib
from typing import Optional, Tuple, Any

# Re-export canonical FSMState so callers have a stable type to reference
from .entry_exit_fsm import FSMState  # noqa: F401


class IFSMEngine:
    """Minimal interface that any FSM engine must implement.

    Implementations may accept additional constructor args, but must at least
    accept: db_manager, outer_scanner_id, inner_scanner_id.
    """

    # Optional: engines can expose these for diagnostics
    outer_scanner_id: str
    inner_scanner_id: str

    def process_detection(self, scanner_id: str, beacon_id: str, rssi: int) -> Optional[Tuple[Any, Any]]:
        """Process a single detection.

        Should return (old_state, new_state) if a state change occurred;
        otherwise return None. The state objects should expose a .value string.
        """
        raise NotImplementedError

    def get_beacon_state(self, beacon_id: str):
        """Return current state object for a beacon (must have .value)."""
        raise NotImplementedError


def build_fsm_engine(db_manager, outer_scanner_id: str, inner_scanner_id: str, **kwargs):
    """Construct the configured FSM engine.

    The engine class is located from env FSM_ENGINE in the form
    "module.path:ClassName". Falls back to EntryExitFSM if not provided.
    Any extra kwargs are forwarded to the engine constructor.
    """
    spec = os.getenv('FSM_ENGINE', 'app.entry_exit_fsm:EntryExitFSM')
    try:
        module_name, class_name = spec.split(':', 1)
    except ValueError:
        module_name, class_name = 'app.entry_exit_fsm', 'EntryExitFSM'

    module = importlib.import_module(module_name)
    engine_cls = getattr(module, class_name)

    # Try to build using canonical signature; fall through to generic if needed
    try:
        return engine_cls(
            db_manager=db_manager,
            outer_scanner_id=outer_scanner_id,
            inner_scanner_id=inner_scanner_id,
            **kwargs,
        )
    except TypeError:
        # Some engines might use positional or different names – pass what we have
        return engine_cls(db_manager, outer_scanner_id, inner_scanner_id, **kwargs)


