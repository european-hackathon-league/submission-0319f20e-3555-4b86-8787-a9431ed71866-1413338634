# /// script
# dependencies = ["beautifulsoup4", "requests"]
# ///
"""Extract messages and original attachments from a user-saved Discord HTML page."""
from pathlib import Path
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone
import json, hashlib, sys
import requests
from bs4 import BeautifulSoup

source=Path(sys.argv[1] if len(sys.argv)>1 else 'archive/discord/bmw-channel.html')
soup=BeautifulSoup(source.read_text(),'html.parser')
messages=[]; attachments={}; author=None
for item in soup.select('[id^="chat-messages-"]'):
    parts=item['id'].split('-'); channel,mid=parts[-2:]
    if channel==mid: continue
    name=item.select_one('[id^="message-username-"]')
    if name:
        username=name.select_one('[data-text]')
        author=username['data-text'] if username else name.get_text(' ',strip=True)
    original_html=str(item)
    content=item.find(id='message-content-'+mid)
    if content:
        for img in content.select('img[alt]'): img.replace_with(img['alt'])
    links=list(dict.fromkeys(a['href'] for a in item.select('a[href]')))
    timestamp=item.select_one('time')
    entry={'id':mid,'channel_id':channel,'author':author,'timestamp':timestamp.get('datetime') if timestamp else None,
        'url':f'https://discord.com/channels/1553151744047976549/{channel}/{mid}',
        'text':content.get_text(' ',strip=True) if content else '', 'links':links,
        'rendered_message_html':original_html}
    messages.append(entry)
    for url in links:
        u=urlparse(url)
        if u.hostname=='cdn.discordapp.com' and '/attachments/' in u.path:
            aid=u.path.split('/')[-2]
            name=unquote(u.path.split('/')[-1])
            dest=Path('archive/discord/attachments')/(aid+'-'+name)
            dest.parent.mkdir(exist_ok=True,parents=True)
            if not dest.exists():
                r=requests.get(url,timeout=120); r.raise_for_status(); dest.write_bytes(r.content)
            attachments[url]={'url':url,'path':str(dest),'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'message_id':mid}
result={'captured_at':datetime.now(timezone.utc).isoformat(),'saved_page':str(source),'messages':messages,'attachments':list(attachments.values())}
(source.parent/'messages.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
md=['# BMW channel transcript','',f'Extracted from `{source.name}`. Raw HTML retained alongside this transcript.','']
for m in messages:
    md.extend([f"## {m['timestamp']} — {m['author']}",'',m['url'],'',m['text'] or '(Attachment-only message)',''])
    md.extend('- '+x for x in m['links'])
    md.append('')
(source.parent/'messages.md').write_text('\n'.join(md))
print(f'{len(messages)} messages; {len(attachments)} original attachments downloaded')
for a in attachments.values(): print(a['path'],a['bytes'])
