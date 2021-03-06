# -*- coding: utf-8 -*- 
# /*
#  * Copyright (C) 2019 PSYGIG株式会社
#  * Copyright (C) 2019 Docker Inc.
#  *
#  * Licensed under the Apache License, Version 2.0 (the "License");
#  * you may not use this file except in compliance with the License.
#  * You may obtain a copy of the License at
#  *
#  * http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing, software
#  * distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.
#  */

from __future__ import absolute_import
from __future__ import unicode_literals

from angelo import utils


class StreamOutputError(Exception):
    pass


def write_to_stream(s, stream):
    try:
        stream.write(s)
    except UnicodeEncodeError:
        encoding = getattr(stream, 'encoding', 'ascii')
        stream.write(s.encode(encoding, errors='replace').decode(encoding))


def stream_output(output, stream):
    is_terminal = hasattr(stream, 'isatty') and stream.isatty()
    stream = utils.get_output_stream(stream)
    lines = {}
    diff = 0

    for event in utils.json_stream(output):
        yield event
        is_progress_event = 'progress' in event or 'progressDetail' in event

        if not is_progress_event:
            print_output_event(event, stream, is_terminal)
            stream.flush()
            continue

        if not is_terminal:
            continue

        # if it's a progress event and we have a terminal, then display the progress bars
        image_id = event.get('id')
        if not image_id:
            continue

        if image_id not in lines:
            lines[image_id] = len(lines)
            write_to_stream("\n", stream)

        diff = len(lines) - lines[image_id]

        # move cursor up `diff` rows
        write_to_stream("%c[%dA" % (27, diff), stream)

        print_output_event(event, stream, is_terminal)

        if 'id' in event:
            # move cursor back down
            write_to_stream("%c[%dB" % (27, diff), stream)

        stream.flush()


def print_output_event(event, stream, is_terminal):
    if 'errorDetail' in event:
        raise StreamOutputError(event['errorDetail']['message'])

    terminator = ''

    if is_terminal and 'stream' not in event:
        # erase current line
        write_to_stream("%c[2K\r" % 27, stream)
        terminator = "\r"
    elif 'progressDetail' in event:
        return

    if 'time' in event:
        write_to_stream("[%s] " % event['time'], stream)

    if 'id' in event:
        write_to_stream("%s: " % event['id'], stream)

    if 'from' in event:
        write_to_stream("(from %s) " % event['from'], stream)

    status = event.get('status', '')

    if 'progress' in event:
        write_to_stream("%s %s%s" % (status, event['progress'], terminator), stream)
    elif 'progressDetail' in event:
        detail = event['progressDetail']
        total = detail.get('total')
        if 'current' in detail and total:
            percentage = float(detail['current']) / float(total) * 100
            write_to_stream('%s (%.1f%%)%s' % (status, percentage, terminator), stream)
        else:
            write_to_stream('%s%s' % (status, terminator), stream)
    elif 'stream' in event:
        write_to_stream("%s%s" % (event['stream'], terminator), stream)
    else:
        write_to_stream("%s%s\n" % (status, terminator), stream)


def get_digest_from_pull(events):
    digest = None
    for event in events:
        status = event.get('status')
        if not status or 'Digest' not in status:
            continue
        else:
            digest = status.split(':', 1)[1].strip()
    return digest


def get_digest_from_push(events):
    for event in events:
        digest = event.get('aux', {}).get('Digest')
        if digest:
            return digest
    return None
