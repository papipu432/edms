"""Prompt injection detection and sanitization for LLM inputs."""

import re


class PromptGuard:
    """Detects and neutralizes prompt injection attempts in user content."""

    # Pattern definitions: (compiled_regex, pattern_name, severity)
    PATTERNS: list[tuple[re.Pattern, str, str]] = [
        # High severity: instruction override patterns
        (
            re.compile(
                r"(?i)\b(ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|guidelines))",
            ),
            "ignore_instructions",
            "high",
        ),
        (
            re.compile(r"(?i)\b(disregard\s+(all\s+)?(above|previous|prior|earlier))"),
            "ignore_instructions",
            "high",
        ),
        (
            re.compile(r"(?i)\b(new\s+instructions\s*:)"),
            "instruction_override",
            "high",
        ),
        (
            re.compile(r"(?i)\b(override\s*:)"),
            "instruction_override",
            "high",
        ),
        (
            re.compile(r"(?i)\b(forget\s+everything)"),
            "instruction_override",
            "high",
        ),
        (
            re.compile(r"(?i)\b(do\s+not\s+follow\s+(the\s+)?(previous|prior|above|earlier|original)\s+(instructions|rules|guidelines))"),
            "instruction_override",
            "high",
        ),
        # Medium severity: role-switching attempts
        (
            re.compile(r"(?i)\b(you\s+are\s+now\s+(?:a|an|the)\s+)"),
            "role_switching",
            "medium",
        ),
        (
            re.compile(r"(?i)\b(pretend\s+to\s+be\s+)"),
            "role_switching",
            "medium",
        ),
        (
            re.compile(r"(?i)\b(act\s+as\s+(?:a|an|the)\s+)"),
            "role_switching",
            "medium",
        ),
        (
            re.compile(r"(?i)\b(as\s+an\s+ai\s*,?\s+you\s+(must|should|will|can))"),
            "role_switching",
            "medium",
        ),
        # Medium severity: delimiter injection
        (
            re.compile(r"</?(system|assistant|user|prompt|instructions?)>", re.IGNORECASE),
            "delimiter_injection",
            "medium",
        ),
        (
            re.compile(r"```\s*(system|instructions?|prompt)\b", re.IGNORECASE),
            "delimiter_injection",
            "medium",
        ),
        # Medium severity: system prompt embedded in user content
        (
            re.compile(r"(?i)^system\s*:", re.MULTILINE),
            "system_prompt_injection",
            "medium",
        ),
    ]

    def sanitize(self, text: str) -> tuple[str, list[dict]]:
        """Sanitize text by detecting and neutralizing prompt injection patterns.

        Returns:
            A tuple of (sanitized_text, detections) where detections is a list of
            dicts with keys: pattern_name, severity, matched_text.
        """
        detections: list[dict] = []
        sanitized = text

        for pattern, pattern_name, severity in self.PATTERNS:
            matches = list(pattern.finditer(sanitized))
            for match in matches:
                detections.append({
                    "pattern_name": pattern_name,
                    "severity": severity,
                    "matched_text": match.group(0),
                })

        if detections:
            # Neutralize by prefixing the entire content to signal it as user data
            sanitized = "[user text]: " + sanitized

        return sanitized, detections

    def wrap_user_content(self, text: str) -> str:
        """Wrap user content in XML boundary markers."""
        return f"<user_content>\n{text}\n</user_content>"
