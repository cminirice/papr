"""只读代码注册表。部署指纹包括数学实现和内容契约，不接受在线代码。"""
from hashlib import sha256
from pathlib import Path

from app.generators import multiplication
from app.schemas import content


def definition() -> dict:
    files = (Path(multiplication.__file__), Path(content.__file__), Path(__file__))
    digest = sha256()
    for path in files:
        digest.update(path.name.encode() + b'\0' + path.read_bytes() + b'\0')
    return {
        'key': multiplication.KEY,
        'version': multiplication.VERSION,
        'validator_version': multiplication.VALIDATOR_VERSION,
        'artifact_hash': digest.hexdigest(),
        'param_schema': content.MultiplicationProfile.model_json_schema(),
        'output_schema': content.MultiplicationQuestion.model_json_schema(),
        'supported_objectives': [multiplication.OBJECTIVE, multiplication.ZERO_OBJECTIVE],
        'supported_question_types': ['answer', 'fill', 'choice'],
        'supported_render_modes': ['vertical', 'direct'],
        'supported_difficulties': ['basic', 'standard', 'challenge'],
    }
