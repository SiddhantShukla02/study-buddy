"""Thin wrapper around Amazon Bedrock's Converse API.

Bedrock is OPTIONAL. It switches on only when BEDROCK_MODEL_ID is set (we deliberately do not
guess a model id: use one your AWS account has been granted access to). Credentials come from the
normal AWS chain (env vars, ~/.aws, or an AWS Bedrock API key in AWS_BEARER_TOKEN_BEDROCK).
Without it, every feature falls back to a rule-based path and nothing breaks.

  BEDROCK_MODEL_ID   e.g. an inference-profile or model id from the Bedrock console
  AWS_REGION         region where that model is enabled (default us-east-1)
"""
import os

_client = None


def model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", "").strip()


def enabled() -> bool:
    return bool(model_id())


def region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def client():
    global _client
    if _client is None:
        import boto3  # imported lazily so the server runs without boto3 installed

        _client = boto3.client("bedrock-runtime", region_name=region())
    return _client


def converse(messages: list, system: str, tools: list | None = None,
             max_tokens: int = 700, temperature: float = 0.2) -> dict:
    """One Bedrock Converse call (blocking). Returns the raw response dict."""
    kwargs = {
        "modelId": model_id(),
        "messages": messages,
        "system": [{"text": system}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if tools:
        kwargs["toolConfig"] = {"tools": tools}
    return client().converse(**kwargs)


def text_of(response: dict) -> str:
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(b.get("text", "") for b in blocks).strip()
