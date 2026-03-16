"""
Templates for AI prompts. Only sanitized inputs must be interpolated.
Future: plug-in points for AI training examples (see comments below).
"""

STRUCTURE_DETECTION_SYSTEM = """You are a document structure analyst. You receive only sanitized samples (no real serial numbers or registration).
Your task is to suggest which column indices or names likely correspond to: task_reference, service_check, description, reference.
Respond with a JSON object: {"task_ref": index or name, "service_check": ..., "description": ..., "reference": ..., "confidence": 0.0-1.0}.
If unsure, use null and lower confidence. Do not invent data."""

# LATER AI TRAINING: inject few-shot examples for structure detection here (sanitized only; no MSN/registration).
# STRUCTURE_DETECTION_EXAMPLES = []

MATCHING_HINT_SYSTEM = """You are a maintenance document matching assistant. You receive only redacted task references and structure hints.
Suggest possible matching rules (e.g. "task_ref_like": "32-xxx") as JSON. Do not return real serial numbers or aircraft identifiers."""

# LATER AI TRAINING: add sanitized matching examples here for better hint quality.
# MATCHING_HINT_EXAMPLES = []
