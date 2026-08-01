import pytest

from app.services.template import TemplateRenderer  # noqa: F401


@pytest.mark.unit
def test_extract_variables():
    template = "Hello {{name}}, your order {{order_id}} is ready"
    vars = TemplateRenderer.extract_required_variables(template)

    assert vars == {"name", "order_id"}


@pytest.mark.unit
def test_extract_no_variables():
    template = "Hello world, no variables here"
    vars = TemplateRenderer.extract_required_variables(template)

    assert len(vars) == 0


@pytest.mark.unit
def test_render_template():
    template = "User {{username}} has {{count}} notifications"
    variables = {"username": "alice", "count": "5"}

    result = TemplateRenderer.render(template, variables)

    assert result == "User alice has 5 notifications"


@pytest.mark.unit
def test_render_template_single_var():
    template = "Alert: {{message}}"
    variables = {"message": "System down"}

    result = TemplateRenderer.render(template, variables)

    assert result == "Alert: System down"


@pytest.mark.unit
def test_render_template_missing_var():
    template = "Hello {{name}}, you have {{count}} items"
    variables = {"name": "bob"}

    with pytest.raises(ValueError) as exc_info:
        TemplateRenderer.render(template, variables)

    assert "count" in str(exc_info.value)


@pytest.mark.unit
def test_validate_variables_success():
    template = "{{var1}} and {{var2}}"
    variables = {"var1": "value1", "var2": "value2", "var3": "extra"}

    validated = TemplateRenderer.validate_variables(template, variables)

    assert validated == {"var1": "value1", "var2": "value2"}


@pytest.mark.unit
def test_validate_variables_missing():
    template = "Required {{missing}} variable"
    variables = {"other": "value"}

    with pytest.raises(ValueError):
        TemplateRenderer.validate_variables(template, variables)


@pytest.mark.unit
def test_template_variable_format():
    template = "Valid: {{var_name}}, {{VAR2}}, {{a1}}"
    vars = TemplateRenderer.extract_required_variables(template)

    assert len(vars) == 3


@pytest.mark.unit
def test_template_complex_rendering():
    template = "Order {{order_id}} for {{customer}} - Status: {{status}} - Amount: {{amount}}"
    variables = {
        "order_id": "ORD-123456",
        "customer": "ACME Corp",
        "status": "Shipped",
        "amount": "$1,234.56",
    }

    result = TemplateRenderer.render(template, variables)

    expected = "Order ORD-123456 for ACME Corp - Status: Shipped - Amount: $1,234.56"
    assert result == expected
