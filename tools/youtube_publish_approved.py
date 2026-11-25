#!/usr/bin/env python3
import argparse, json, os, pathlib, sys
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


def refresh_youtube_credentials(credentials):
    retries = Retry(
        total=2,
        connect=0,
        read=0,
        other=0,
        allowed_methods={"POST"},
        status_forcelist=(502,),
        backoff_factor=15,
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    # Only the token endpoint is retried, before any YouTube upload request.
    with requests.Session() as session:
        session.mount(credentials.token_uri, HTTPAdapter(max_retries=retries))
        credentials.refresh(Request(session=session))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--video-url', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--description', required=True)
    p.add_argument('--tags', default='KI,Technologie,TAYVORIQ,Shorts')
    p.add_argument('--privacy', default='private', choices=['private','unlisted','public'])
    p.add_argument('--output', default='youtube-result.json')
    a=p.parse_args()

    client_id=os.environ['YOUTUBE_CLIENT_ID']
    client_secret=os.environ['YOUTUBE_CLIENT_SECRET']
    refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN']

    out=pathlib.Path('approved-video.mp4')
    with requests.get(a.video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with out.open('wb') as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)
    if out.stat().st_size < 1_000_000:
        raise RuntimeError('Video download too small')

    creds=Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/youtube.upload'],
    )
    refresh_youtube_credentials(creds)
    youtube=build('youtube','v3',credentials=creds,cache_discovery=False)
    body={
        'snippet': {
            'title': a.title[:100],
            'description': a.description,
            'tags': [x.strip() for x in a.tags.split(',') if x.strip()],
            'categoryId':'28',
            'defaultLanguage':'de',
            'defaultAudioLanguage':'de',
        },
        'status': {
            'privacyStatus':a.privacy,
            'selfDeclaredMadeForKids':False,
        },
    }
    media=MediaFileUpload(str(out),mimetype='video/mp4',resumable=True,chunksize=8*1024*1024)
    request=youtube.videos().insert(part='snippet,status',body=body,media_body=media)
    response=None
    while response is None:
        status,response=request.next_chunk()
        if status:
            print(f'upload_progress={int(status.progress()*100)}%')
    result={'video_id':response['id'],'url':f"https://www.youtube.com/shorts/{response['id']}",'privacy':a.privacy}
    pathlib.Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    main()
