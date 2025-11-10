"""
Configuration loader for prompt templates and settings
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """Configuration manager for the application"""

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.config_dir = self.base_dir / "config"
        self.prompts_file = self.config_dir / "prompts.yaml"

        # Load configuration
        self.prompts = self._load_prompts()

        # Provider settings (vllm or openrouter)
        self.provider = os.getenv("PROVIDER", "vllm").lower()

        # vLLM settings
        self.model_name = os.getenv("MODEL_NAME", "Qwen/Qwen2-VL-7B-Instruct")
        self.vllm_host = os.getenv("VLLM_HOST", "localhost")
        self.vllm_port = int(os.getenv("VLLM_PORT", "8000"))
        self.vllm_api_base = f"http://{self.vllm_host}:{self.vllm_port}/v1"

        # OpenRouter settings
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-vl-8b-instruct")

        # API settings
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE_MB", "10")) * 1024 * 1024  # Convert to bytes
        self.allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}

    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompt templates from YAML file"""
        if not self.prompts_file.exists():
            raise FileNotFoundError(f"Prompts file not found: {self.prompts_file}")

        with open(self.prompts_file, 'r') as f:
            prompts = yaml.safe_load(f)

        return prompts

    def get_prompt_template(self, template_name: str) -> Dict[str, str]:
        """Get a specific prompt template by name"""
        if template_name not in self.prompts:
            raise ValueError(f"Template '{template_name}' not found. Available templates: {list(self.prompts.keys())}")

        return self.prompts[template_name]

    def get_available_templates(self) -> Dict[str, str]:
        """Get list of available template names with descriptions"""
        return {
            name: template.get("description", "")
            for name, template in self.prompts.items()
        }

    def reload_prompts(self):
        """Reload prompt templates from file"""
        self.prompts = self._load_prompts()


# Global config instance
config = Config()
