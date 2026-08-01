import re
from re import Match


class TemplateRenderer:
    """Render notification templates with variable substitution."""

    VAR_PATTERN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")

    @staticmethod
    def validate_variables(template: str, provided_vars: dict[str, str]) -> dict[str, str]:
        """Extract required variables from template and validate against provided ones."""
        required_vars = set(TemplateRenderer.VAR_PATTERN.findall(template))
        missing_vars = required_vars - set(provided_vars.keys())

        if missing_vars:
            raise ValueError(f"Missing required variables: {', '.join(sorted(missing_vars))}")

        return {k: v for k, v in provided_vars.items() if k in required_vars}

    @staticmethod
    def render(template: str, variables: dict[str, str]) -> str:
        """Render template with variable substitution."""
        TemplateRenderer.validate_variables(template, variables)

        def replace_var(match: Match[str]) -> str:
            var_name = match.group(1)
            return variables.get(var_name, "")

        return TemplateRenderer.VAR_PATTERN.sub(replace_var, template)

    @staticmethod
    def extract_required_variables(template: str) -> set[str]:
        """Extract all required variable names from template."""
        return set(TemplateRenderer.VAR_PATTERN.findall(template))
