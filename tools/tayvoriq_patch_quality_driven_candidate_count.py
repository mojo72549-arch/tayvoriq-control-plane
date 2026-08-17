#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path('.github/workflows/tayvoriq-agent-orchestrator-v2.yml')


def main() -> int:
    text = PATH.read_text(encoding='utf-8')
    text = text.replace('      - name: Generate grounded 5-trend ranking\n', '      - name: Generate quality-driven 1-5 trend ranking\n')

    old_contract = '''          trends=d.get('trends') or []
          if d.get('mode') == 'active_series':
              assert len(trends) == 1
              assert [x.get('id') for x in trends] == ['1']
              sc=trends[0].get('source_context') or {}
              series=sc.get('series_context') or {}
              assert series.get('series_id') and int(series.get('episode') or 0) >= 1
              assert series.get('hook') and series.get('bridge_out') and series.get('red_thread')
          else:
              assert len(trends) == 5
              assert [x.get('id') for x in trends] == ['1','2','3','4','5']
          for t in trends:
'''
    new_contract = '''          trends=d.get('trends') or []
          assert 1 <= len(trends) <= 5, f"quality-driven candidate count must be 1-5, got {len(trends)}"
          assert [x.get('id') for x in trends] == [str(i) for i in range(1, len(trends)+1)]
          if d.get('mode') == 'active_series':
              sc=trends[0].get('source_context') or {}
              series=sc.get('series_context') or {}
              assert series.get('series_id') and int(series.get('episode') or 0) >= 1
              assert series.get('hook') and series.get('bridge_out') and series.get('red_thread')
          for t in trends:
'''
    if old_contract not in text:
        raise RuntimeError('approval contract anchor not found')
    text = text.replace(old_contract, new_contract, 1)

    old_keyboard = '''              kb={'inline_keyboard':[[
                  {'text':'1️⃣ Trend 1','callback_data':f'select_trend:{sid}:1'},
                  {'text':'2️⃣ Trend 2','callback_data':f'select_trend:{sid}:2'}],[
                  {'text':'3️⃣ Trend 3','callback_data':f'select_trend:{sid}:3'},
                  {'text':'4️⃣ Trend 4','callback_data':f'select_trend:{sid}:4'}],[
                  {'text':'5️⃣ Trend 5','callback_data':f'select_trend:{sid}:5'}]]}
'''
    new_keyboard = '''              labels={'1':'1️⃣','2':'2️⃣','3':'3️⃣','4':'4️⃣','5':'5️⃣'}
              buttons=[{'text':f"{labels.get(str(t['id']), str(t['id']))} Trend {t['id']}",'callback_data':f"select_trend:{sid}:{t['id']}"} for t in d['trends']]
              kb={'inline_keyboard':[buttons[i:i+2] for i in range(0,len(buttons),2)]}
'''
    if old_keyboard not in text:
        raise RuntimeError('Telegram keyboard anchor not found')
    text = text.replace(old_keyboard, new_keyboard, 1)

    old_copy = "              lines += ['', 'Aktuell geprüft · mindestens 2 Quellen je Trend · Qualität vor Geschwindigkeit.', '', 'Schritt 1: Trendnummer wählen.',"
    new_copy = "              lines += ['', f\"{len(d['trends'])} starke Trend{'s' if len(d['trends']) != 1 else ''} haben heute alle Gates bestanden · mindestens 2 Quellen je Trend · Qualität bestimmt die Anzahl.\", '', 'Schritt 1: Trendnummer wählen.',"
    if old_copy not in text:
        raise RuntimeError('Telegram copy anchor not found')
    text = text.replace(old_copy, new_copy, 1)

    PATH.write_text(text, encoding='utf-8')
    print({'patched': str(PATH), 'policy': 'quality-driven 1-5; rescan only on zero'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
