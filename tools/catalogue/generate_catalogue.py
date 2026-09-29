from pathlib import Path
import re,json,hashlib,argparse
import os
PACKAGE=Path(__file__).resolve().parents[2]
ROOT=Path(os.environ.get('STYLIST_SERVER_ROOT', str(PACKAGE.parent/'rathena-stylist-ui'))).resolve()
SOURCE=PACKAGE/'client/source/stylingshopinfo.lub'
OUT=PACKAGE/'generated/db/re/stylist_modern.yml'
FUNCTIONS={'AddHeadPalette':('Hair_Color','CostsHuman'), 'AddHeadStyle':('Hair','CostsHuman'), 'AddDoramHeadStyle':('Hair','CostsDoram'), 'AddBodyPalette':('Clothes_Color','CostsHuman'), 'AddDoramBodyPalette':('Clothes_Color','CostsDoram'), 'AddTopAccessory':('Head_Top','CostsHuman'), 'AddMidAccessory':('Head_Mid','CostsHuman'), 'AddBottomAccessory':('Head_Bottom','CostsHuman')}

NONE=0xFFFF
FIELDS=['second','trans','third','third_t','alternate','fourth']
TIERS={'second':2,'trans':3,'third':4,'third_t':4,'fourth':5}

def job_ids():
 # Resolve the actual job constants; do not duplicate client IDs in Python.
 enum=(ROOT/'src/common/mmo.hpp').read_text(encoding='utf-8-sig').split('enum e_job {',1)[1].split('};',1)[0]
 jobs={};value=-1
 for name,explicit in re.findall(r'\b(JOB_\w+)\s*(?:=\s*(\d+))?\s*,',enum):
  value=int(explicit) if explicit else value+1;jobs[name]=value
 jobs['STYLIST_NONE']=NONE
 return jobs

def lineage_pairs(include_fourth=True,full=True):
 # full mirrors stylist::lineage_allows: every job of a branch wears every
 # outfit of the branch. full=False is the earlier rule (earlier tiers plus the
 # fourth job), kept only so already published indices stay in place.
 jobs=job_ids();sexes={'SEX_FEMALE':0,'SEX_MALE':1,'SEX_BOTH':2};pairs={}
 definition=(ROOT/'src/map/stylist.hpp').read_text(encoding='utf-8')
 for args in re.findall(r'^STYLIST_LINEAGE\((.*)\)$',definition,re.M):
  parts=[p.strip() for p in args.split(',')];sex=sexes[parts[0]]
  row=dict(zip(FIELDS,[jobs[p] for p in parts[1:]]));assert len(parts)==len(FIELDS)+1,args
  third=row['third_t'] if row['third_t']!=NONE else row['third']
  for field,tier in TIERS.items():
   origin=row[field]
   if origin==NONE:continue
   if full:
    targets=[origin,row['second'],row['trans'],third if tier!=4 else NONE,row['alternate'],row['fourth']]
   else:
    targets=[origin,
     row['second'] if tier>2 else NONE,
     row['trans'] if tier>3 else NONE,
     third if tier>4 else NONE,
     row['alternate'] if tier>=4 else NONE,
     row['fourth'] if include_fourth else NONE]
   for target in targets:
    if target==NONE:continue
    key=(origin,target)
    pairs[key]=sex if key not in pairs or pairs[key]==sex else 2
 return pairs

def generate(source_text=None):
 text=SOURCE.read_text(encoding='utf-8-sig') if source_text is None else source_text
 source_bytes=SOURCE.read_bytes() if source_text is None else source_text.encode('utf-8')
 catalog={};names={}
 for file in (ROOT/'db/re').glob('item_db_*.yml'):
  for m in re.finditer(r'^  - Id: (\d+)\n    AegisName: (\S+)',file.read_text(encoding='utf-8-sig'),re.M): names[int(m[1])]=m[2]
 counters={}; disabled=[];client_lines=[]
 for line in text.splitlines():
  m=re.fullmatch(r'StylingShop\.(Add\w+)\((.*?)\)',line.strip())
  if not m:
   client_lines.append(line);continue
  fn,args=m.groups();nums=[int(v) for v in args.split('{')[0].rstrip(', ').split(',')]; costs=dict((k,int(v)) for k,v in re.findall(r'(zeny|itid|boxitid)\s*=\s*(\d+)',args));flags=re.findall(r'\b(true|false)\b',args)
  if fn=='AddCostumeChange':
   index,origin,target=nums
   # This upstream does not implement the 4355 playable class or 4353 sprite.
   if origin==4355:
    disabled.append({'index':index,'origin':origin,'target':target,'reason':'Original job is not implemented by this rAthena base'})
    client_lines.append('-- Not supported by this server base: '+line);continue
   catalog.setdefault('Body2',{})[index]={'Value':target,'Jobs':[origin],'CostsHuman':costs,'CostsDoram':costs}
  elif fn in FUNCTIONS:
   look,race=FUNCTIONS[fn];counters[fn]=counters.get(fn,0)+1;index=counters[fn]
   entry=catalog.setdefault(look,{}).setdefault(index,{'Value':nums[0]})
   assert entry['Value']==nums[0],(fn,index)
   entry[race]=costs
   if fn in ['AddHeadPalette','AddTopAccessory','AddMidAccessory','AddBottomAccessory'] and flags and flags[0]=='true':entry['CostsDoram']=costs
   if fn=='AddDoramHeadStyle':entry['ColorableDoram']=(flags[0]=='true') if flags else True
  elif fn not in ['AddSecondCostume','AddDoramSecondCostume']:raise ValueError(fn)
  client_lines.append(line)
 catalog.setdefault('Hair_Color',{})[-1]={'Value':0,'CostsHuman':{'zeny':0},'CostsDoram':{'zeny':0}}
 catalog['Clothes_Color'][-1]={'Value':0,'CostsHuman':{'zeny':0},'CostsDoram':{'zeny':0}}
 # Keep all existing indices stable. The client sizes CostumeChange with Lua's
 # length operator and walks it with an index cursor, so extensions must follow
 # the official entries without gaps. Disabled official entries stay in the
 # client table (no player can hold their origin job; the server rejects them).
 lineage_client=[line.replace('-- Not supported by this server base: ','',1)+' -- Not supported by this server base' if line.startswith('-- Not supported by this server base: ') else line for line in client_lines]
 lineage_client+=['','-- Requires stylist_class_lineage: on on the server.']
 existing={(e['Jobs'][0],e['Value']) for e in catalog['Body2'].values()}
 index=max([*catalog['Body2'],*(d['index'] for d in disabled)])+1;lineage_count=0
 # Published order: earlier rule without fourth jobs, then its fourth-job
 # additions, then the full-branch additions. Existing indices never move.
 first=lineage_pairs(include_fourth=False,full=False)
 second=lineage_pairs(full=False)
 complete=lineage_pairs()
 assert set(second)<=set(complete)
 keys=sorted(first)+sorted(set(second)-set(first))+sorted(set(complete)-set(second))
 ordered=[(pair,complete[pair]) for pair in keys]
 for (origin,target),sex in ordered:
  if (origin,target) in existing:continue
  costs={'zeny':0} if origin==target else {'itid':6959,'boxitid':6959}
  race='CostsDoram' if origin in (4218,4220,4308) else 'CostsHuman'
  catalog['Body2'][index]={'Value':target,'Jobs':[origin],race:costs,'LineageOnly':True,'RequiredSex':sex}
  price='zeny = 0' if origin==target else 'itid = 6959, boxitid = 6959'
  lineage_client.append(f'StylingShop.AddCostumeChange({index}, {origin}, {target}, {{ {price} }})')
  index+=1;lineage_count+=1
 assert index <= 32767, 'Stylist indices exceed the server index type'
 lines=['# Generated by tools/catalogue/generate_catalogue.py. Edit source Lua/lineages, then regenerate.','# Client table attribution is preserved in client/stylist/source/stylingshopinfo.lub.','Header:','  Type: STYLIST_DB','  Version: 2','','Body:']
 for look,entries in catalog.items():
  lines+=['  - Look: '+look,'    Options:']
  for index,e in sorted(entries.items()):
   value=names[e['Value']] if look.startswith('Head_') else e['Value']
   lines += [f'      - Index: {index}',f'        Value: {value}']
   if 'Jobs' in e:
    lines += [f"        RequiredJob: {e['Jobs'][0]}"]
   if 'ColorableDoram' in e:lines+=['        ColorableDoram: '+str(e['ColorableDoram']).lower()]
   if e.get('LineageOnly'):lines+=['        LineageOnly: true','        RequiredSex: '+str(e['RequiredSex'])]
   for race in ['CostsHuman','CostsDoram']:
    if race not in e:continue
    lines+=['        '+race+':']
    cost=e[race];lines += ['          Price: '+str(cost.get('zeny',0))]
    for key,yaml in [('itid','RequiredItem'),('boxitid','RequiredItemBox')]:
     if cost.get(key):lines+=['          '+yaml+': '+names[cost[key]]]
 payload='\n'.join(lines)+'\n';client='\n'.join(client_lines)+'\n'
 return payload,client,{'source_sha256':hashlib.sha256(source_bytes).hexdigest(),'counts':{k:len(v) for k,v in catalog.items()},'lineage_only':lineage_count,'disabled':disabled},'\n'.join(lineage_client)+'\n'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 yml,lua,summary,lineage=generate();outputs={OUT:yml,PACKAGE/'generated/client/Files/data/luafiles514/lua files/stylingshop/stylingshopinfo.lub':lua,PACKAGE/'generated/client/LineageFiles/data/luafiles514/lua files/stylingshop/stylingshopinfo.lub':lineage,PACKAGE/'generated/catalogue.json':json.dumps(summary,indent=2)+'\n'}
 for path,data in outputs.items():
  if args.check:
   assert path.read_text(encoding='utf-8')==data,'Generated file differs: '+str(path)
  else:
   path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data,encoding='utf-8',newline='\n')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
