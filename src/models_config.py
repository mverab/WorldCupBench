"""
Configuration of the SOTA AI models (June 2026) participating in WorldCupBench.

Each entry defines:
- name: human-readable model name (used to name prediction files).
- model_id: model identifier in OpenRouter.
- provider: lab/company that develops the model.

NOTE: The `model_id` values follow the OpenRouter convention (provider/model). As
these are cutting-edge models (June 2026), verify the exact identifiers available
at https://openrouter.ai/models and adjust them if necessary.
"""

# List of State-Of-The-Art models to compare in the benchmark (June 2026).
MODELS = [
    {
        "name": "GPT-5.5",
        "model_id": "openai/gpt-5.5",
        "provider": "OpenAI",
    },
    {
        "name": "Claude-Fable-5",
        "model_id": "anthropic/claude-fable-5",
        "provider": "Anthropic",
    },
    {
        "name": "Gemini-3.5-Flash",
        "model_id": "google/gemini-3.5-flash",
        "provider": "Google",
    },
    {
        "name": "Grok-4.3",
        "model_id": "x-ai/grok-4.3",
        "provider": "xAI",
    },
    {
        "name": "DeepSeek-V4-Pro",
        "model_id": "deepseek/deepseek-v4-pro",
        "provider": "DeepSeek",
    },
    {
        "name": "Qwen-3.7-Max",
        "model_id": "qwen/qwen-3.7-max",
        "provider": "Alibaba",
    },
    {
        "name": "Kimi-K2.6",
        "model_id": "moonshotai/kimi-k2.6",
        "provider": "Moonshot AI",
    },
    {
        "name": "GLM-5.1",
        "model_id": "z-ai/glm-5.1",
        "provider": "Zhipu AI",
    },
    {
        "name": "MiniMax-M3",
        "model_id": "minimax/minimax-m3",
        "provider": "MiniMax",
    },
    {
        "name": "MiMo-V2.5-Pro",
        "model_id": "xiaomi/mimo-v2.5-pro",
        "provider": "Xiaomi",
    },
    {
        "name": "Nex-N2-Pro",
        "model_id": "nex-agi/nex-n2-pro:free",
        "provider": "Nex AGI",
    },
]


def get_model_by_name(name: str):
    """Returns a model's configuration from its name."""
    for model in MODELS:
        if model["name"].lower() == name.lower():
            return model
    return None
