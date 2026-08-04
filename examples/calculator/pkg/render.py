import json


def format_json_output(expression: str, result: float, indent: int = 2) -> str:
    result_to_dump = (
        int(result) if isinstance(result, float) and result.is_integer() else result
    )

    output_data = {
        "expression": expression,
        "result": result_to_dump,
    }
    return json.dumps(output_data, indent=indent)
