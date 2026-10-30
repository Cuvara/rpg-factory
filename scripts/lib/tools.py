"""Optional adapter tool discovery; failures always degrade to None."""
import argparse, json, os, platform, shutil, subprocess, sys
from pathlib import Path

OPTIONAL_PROVIDERS={'game-art-mcp','ai-pixel-art-image-generation','figma'}

def _provider_config_names(name):
    """Discover configured MCP/plugin names without returning configuration values."""
    home=Path.home(); cwd=Path.cwd()
    settings=[]
    for env_name, default in (('RPG_FACTORY_CLAUDE_SETTINGS',home/'.claude'/'settings.json'),
                              ('RPG_FACTORY_PROJECT_SETTINGS',cwd/'.claude'/'settings.json'),
                              ('RPG_FACTORY_PROJECT_SETTINGS_LOCAL',cwd/'.claude'/'settings.local.json'),
                              ('RPG_FACTORY_USER_MCP_FILE',home/'.claude.json'),
                              ('RPG_FACTORY_MCP_FILE',cwd/'.mcp.json')):
        settings.append(Path(os.environ.get(env_name,default)))
    plugin_file=Path(os.environ.get('RPG_FACTORY_INSTALLED_PLUGINS',home/'.claude'/'plugins'/'installed_plugins.json'))
    for path in settings:
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            continue
        mcp=data.get('mcpServers',{})
        if isinstance(mcp,dict) and name in mcp: return 'mcp'
        plugins=data.get('enabledPlugins',{})
        if isinstance(plugins,dict) and any(str(k).split('@',1)[0]==name and v for k,v in plugins.items()): return 'plugin'
    try:
        data=json.loads(plugin_file.read_text(encoding='utf-8'))
        rows=data.get('plugins',data) if isinstance(data,dict) else data
        if isinstance(rows,dict) and any(str(k).split('@',1)[0]==name for k in rows): return 'plugin'
        if isinstance(rows,list) and any(isinstance(x,dict) and x.get('name')==name for x in rows): return 'plugin'
    except (OSError,ValueError): pass
    return None

def find_tool(name):
    key=name.upper().replace('-','_')
    override=os.environ.get('RPG_FACTORY_TOOL_'+key)
    if name in OPTIONAL_PROVIDERS:
        if override:
            return {'name':name,'source':'environment override'}
        source=_provider_config_names(name)
        return {'name':name,'source':source} if source else None
    candidates=[override] if override else []
    if not override:
        binary={'blender':'blender','unity':'Unity','ffmpeg':'ffmpeg','node':'node'}.get(name)
        if binary and shutil.which(binary): candidates.append(shutil.which(binary))
        if name=='blender' and os.name=='nt':
            base=r'C:\Program Files\Blender Foundation'
            try: candidates += [os.path.join(base,x,'blender.exe') for x in os.listdir(base)]
            except OSError: pass
        if name=='blender' and sys.platform=='darwin': candidates += ['/Applications/Blender.app/Contents/MacOS/Blender']
        if name=='blender' and os.name!='nt' and sys.platform!='darwin': candidates += ['/usr/bin/blender','/usr/local/bin/blender','/snap/bin/blender','/opt/blender/blender']
        if name=='unity':
            for base in (os.path.expandvars(r'%ProgramFiles%\Unity\Hub\Editor'),os.path.expanduser('~/Unity/Hub/Editor'),'/Applications/Unity/Hub/Editor','/opt/unity/editors'):
                try: candidates += [os.path.join(base,v,'Editor','Unity.exe' if os.name=='nt' else 'Unity') for v in os.listdir(base)]
                except OSError: pass
    if name=='pillow':
        try:
            from PIL import __version__
            return {'name':name,'path':'python:PIL','version':__version__}
        except Exception: return None
    for path in candidates:
        if not path or not os.path.isfile(path): continue
        if name in ('unity','blender'):
            resolved=os.path.abspath(path)
            version=Path(path).parent.parent.name if name=='unity' and Path(path).parent.name.lower()=='editor' else ''
            return {'name':name,'path':resolved,'version':version}
        try:
            command=[sys.executable,path,'--version'] if path.lower().endswith('.py') else [path,'--version']
            r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=3)
            version=(r.stdout or r.stderr).strip().splitlines()[0][:160]
            return {'name':name,'path':os.path.abspath(path),'version':version}
        except Exception: return {'name':name,'path':os.path.abspath(path),'version':''}
    return None

def main():
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    parser=argparse.ArgumentParser(); parser.add_argument('name'); args=parser.parse_args()
    result=find_tool(args.name); print(json.dumps(result,sort_keys=True) if result else 'null')
    return 0

if __name__ == '__main__':
    sys.exit(main())
