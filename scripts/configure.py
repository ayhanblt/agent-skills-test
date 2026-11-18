"""Prompt for local credentials without echo or shell-history exposure."""
import argparse,getpass,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def store_secret(name,value):
    if not value or any(c.isspace() for c in value):raise ValueError('Empty or malformed credential')
    folder=ROOT/'.local';folder.mkdir(mode=0o700,exist_ok=True);folder.chmod(0o700)
    path=folder/'secrets.json'
    if path.is_symlink():raise ValueError('Refusing a symlink for secrets.json')
    data=json.loads(path.read_text()) if path.exists() else {}
    data[name]=value
    fd,tmp=tempfile.mkstemp(dir=folder,prefix='.secrets-')
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--typesafe',action='store_true');group.add_argument('--claude',action='store_true');args=p.parse_args()
    name='TYPESAFE_API_KEY' if args.typesafe else 'CLAUDE_CODE_OAUTH_TOKEN'
    value=getpass.getpass(name+' (input hidden): ').strip()
    store_secret(name,value)
    print('Saved locally. No credential value was printed; .local/ is excluded from Git.')
if __name__=='__main__':main()
