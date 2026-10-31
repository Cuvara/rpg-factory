"""Optional concept-draft image provider discovery; performs no network calls."""
from datetime import date
import sys


PROVIDERS = ('game-art-mcp', 'ai-pixel-art-image-generation')


def inspect_provider(ctx, prompt, generated_by='art-2d', model=None, artifact_id=None):
    """Return a draft provenance record or an explicit unavailable result.

    The adapter only checks whether a provider is exposed by the workflow context.
    Provider invocation and image transport stay outside quality checks.
    """
    tools = getattr(ctx, 'tools', None)
    available = []
    for name in PROVIDERS:
        try:
            provider = tools(name) if callable(tools) else None
        except Exception:
            provider = None
        if provider:
            available.append((name, provider))
    if not available:
        return {
            'state': 'NOT_AVAILABLE',
            'reason': 'No optional image provider is exposed by ctx.tools(game-art-mcp or ai-pixel-art-image-generation).',
            'artifact': None,
        }
    name, provider = available[0]
    if callable(provider):
        provider = getattr(provider, 'name', None) or name
    provider_name = provider.get('name', name) if isinstance(provider, dict) else name
    provider_model = model or (provider.get('model') if isinstance(provider, dict) else None) or 'unspecified'
    artifact = {
        'kind': 'concept-2d',
        'domain': 'art2d',
        'schema_version': 2,
        'status': 'draft',
        'title': 'Concept draft: ' + prompt[:120],
        'upstream': [],
        'sources': [],
        'authors': [{'kind': 'agent', 'id': generated_by}],
        'acceptance': [],
        'trace': [],
        'provenance': {
            'generated_by': generated_by,
            'tool': provider_name,
            'model': provider_model,
        },
        'spec': {
            'subject_type': 'prop-item',
            'description': 'Generated concept draft: ' + prompt,
            'stage': 'concept',
            'prompt': prompt,
            'generated_on': date.today().isoformat(),
        },
    }
    if artifact_id:
        artifact['id'] = artifact_id
    return {
        'state': 'HUMAN_REQUIRED',
        'reason': 'Provider is available; generated imagery remains a concept draft pending human review.',
        'artifact': artifact,
    }


if __name__ == '__main__':
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, 'reconfigure'):
            _stream.reconfigure(encoding='utf-8', errors='replace')
