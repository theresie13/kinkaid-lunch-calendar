#!/usr/bin/env python3
"""Publish a rolling SAGE Dining iCalendar feed. Requires requests."""
import datetime as dt
import json
import os
from pathlib import Path
import requests

MENU_ID = os.environ.get('SAGE_MENU_ID', '140085')
ENDPOINT = 'https://www.sagedining.com/microsites/getWeeklyMenuItems'
SOURCE = 'https://www.sagedining.com/sites/kinkaid/menu'
CATEGORIES = ['Entrées', 'Soups', 'Salads', 'Sides and Vegetables', 'Desserts']


def escape(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace(',', '\\,').replace(';', '\\;')


def fold(line):
    # iCalendar content lines must not exceed 75 octets; continuation starts with space.
    result = []
    part = ''
    for char in line:
        if len((part + char).encode('utf-8')) > (75 if not result else 74):
            result.append(part)
            part = ' ' + char
        else:
            part += char
    result.append(part)
    return '\r\n'.join(result)


def get_week(session, sunday):
    response = session.get(ENDPOINT, params={'menuId': MENU_ID, 'date': f'{sunday.month}/{sunday.day}/{sunday.year}'}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError('Unexpected SAGE response format')
    return data


def get_items(day, category):
    values = day.get(category, [])
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(item['name'].strip() for item in values if isinstance(item, dict) and item.get('name') and str(item.get('meal', 'Lunch')).lower() == 'lunch'))


def build():
    today = dt.date.today()
    first_sunday = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    session = requests.Session()
    session.headers.update({'User-Agent': 'KinkaidLunchCalendar/1.0 (public menu calendar)'})
    entries = {}
    successful = 0
    for offset in range(0, 42, 7):
        sunday = first_sunday + dt.timedelta(days=offset)
        try:
            week = get_week(session, sunday)
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            print(f'Warning: could not retrieve {sunday}: {exc}')
            continue
        successful += 1
        for date_text, day in week.items():
            if not isinstance(day, dict):
                continue
            try:
                day_date = dt.datetime.strptime(date_text, '%m/%d/%Y').date()
            except ValueError:
                continue
            if day_date < today or day_date.weekday() >= 5:
                continue
            entrees = get_items(day, 'Entrées')
            if not entrees:
                continue
            entries[day_date] = {category: get_items(day, category) for category in CATEGORIES}
    if successful == 0 or not entries:
        raise RuntimeError('No upcoming lunch entries were retrieved; refusing to overwrite the calendar.')
    now = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Kinkaid LS Lunch//SAGE Feed//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:Kinkaid LS Lunch', 'X-WR-CALDESC:Unofficial Kinkaid Lower School lunch menu from SAGE Dining']
    for date, cats in sorted(entries.items()):
        title = 'Lunch: ' + ' / '.join(cats['Entrées'])
        desc = '\n'.join(f'{category}: ' + (', '.join(cats[category]) or 'None listed') for category in CATEGORIES)
        desc += '\nSource: ' + SOURCE + '\nMenus are subject to change.'
        lines += ['BEGIN:VEVENT', 'UID:kinkaid-ls-lunch-' + date.strftime('%Y%m%d') + '@theresie13.github.io', 'DTSTAMP:' + now, 'DTSTART;VALUE=DATE:' + date.strftime('%Y%m%d'), 'DTEND;VALUE=DATE:' + (date + dt.timedelta(days=1)).strftime('%Y%m%d'), 'SUMMARY:' + escape(title), 'DESCRIPTION:' + escape(desc), 'URL:' + SOURCE, 'END:VEVENT']
    lines += ['END:VCALENDAR']
    output = '\r\n'.join(fold(line) for line in lines) + '\r\n'
    Path('lunch.ics').write_bytes(output.encode('utf-8'))
    print(f'Wrote {len(entries)} lunch events from {successful} successful weekly requests.')


if __name__ == '__main__':
    build()
