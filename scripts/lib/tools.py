"""Optional adapter tool discovery; failures always degrade to None."""
import argparse, json, os, platform, shutil, subprocess, sys

def find_tool(name):
    key=name.upper().replace('-','_')
    override=os.environ.get('RPG_FACTORY_TOOL_'+key)
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
