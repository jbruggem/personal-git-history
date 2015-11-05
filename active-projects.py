#!/usr/bin/env python3.4

import subprocess
import os
from elasticsearch import Elasticsearch
import elasticsearch.helpers

CACHE_DIRS = './cache-dirs'
SEARCH_ROOT = '~'
# REGEX = "jehan"
REGEX = "(jehan|bruggem)"

FIND_ES_IP=['docker', 'inspect', '--format', '{{ .NetworkSettings.IPAddress }}', 'personalgithistory_es_1']
INDEX_NAME="personal-git-history"
COMMIT_DOC_TYPE = 'commit'

RESET_INDEX = True
DEBUG = False


def main():
    repos = []
    if not os.path.exists(CACHE_DIRS):
        print('Finding all repos')
        # " ! -readable -prune " will skip non-readable files
        res = run( 'find %s -type d ! -perm -g+r,u+r,o+r -prune -o -name .git -print' % expand(SEARCH_ROOT))
        print('Done.')
        repos = set(res.splitlines())
        open(CACHE_DIRS, 'w').write("\n".join(repos))
    else:
        print('Not finding all repos, using %s as list of repos' % CACHE_DIRS)
        repos = set(open(CACHE_DIRS, 'r').readlines())

    es = Elasticsearch(run(FIND_ES_IP)+'9200')

    if RESET_INDEX: reset_es(es)

    print('parsing logs')

    log_command = [
        'git', 'log', '-i', '-E',
        '--author=%s' % REGEX,
        '--committer=%s' % REGEX,
        '--pretty=format:"%H ;! %an ;! %ae ;! %ad ;!  %cn ;! %ce ;! %cd ;!  %s"',
        '--date=iso',
    ]

    for r in repos:
        repo_dir = os.path.dirname(r)
        try:
            log = run(log_command, repo_dir, stderr=subprocess.STDOUT)
            parsed = parse(repo_dir, log.splitlines())
            if parsed:
                insert(es, parsed)
        except subprocess.CalledProcessError as e:
            if DEBUG:
                print('\nfailed for this repo')
                print(repo_dir)
                print(e)
                print(e.output)
                print("\n")


def run(cmd, cwd=None, stderr=None):
    if not isinstance(cmd, list):
        cmd = cmd.split(' ')

    return subprocess.check_output(cmd, universal_newlines=True, cwd=cwd, stderr=stderr)

def expand(path):
    return os.path.expanduser(path)

def format_date(d):
    d = d.split(' ')
    d = d[0]+'T'+d[1]+d[2][0:3]+':'+d[2][3:5]
    print(d)
    return d

def parse_line(line):
    elems = line.split(' ;! ')
    return {
        'hash': elems[0],
        'author_name': elems[1],
        'author_email': elems[2],
        'author_date': format_date(elems[3]),
        'committer_name': elems[4],
        'committer_email': elems[5],
        'committer_date': format_date(elems[6]),
        'message': elems[7],
    }

def insert(es, parsed):
    actions = [{"_index": INDEX_NAME, "_id": line['hash'], "_type": COMMIT_DOC_TYPE, '_source': line} for line in parsed]
    res = elasticsearch.helpers.bulk(es, actions)
    print("insert: ",res)

def parse(dir, log):
    if 0 == len(log): return
    print(dir)
    lines = [parse_line(l) for l in log]
    # print(lines[0:5])
    print("Number of matching commits: %d \n" % len(lines))
    return lines
    # create list of commits
    # keep unique hashs

def reset_es(es):
    res = es.indices.delete(index=INDEX_NAME, ignore=404)
    print(res)

    res = es.indices.create(index=INDEX_NAME, body={
            "mappings": {
                COMMIT_DOC_TYPE: {
                    "properties": {
                        'hash': {"type": "string", "index": "not_analyzed"},
                        'author_name': {"type": "string"},
                        'author_email': {"type": "string", "index": "not_analyzed"},
                        'author_date': {"type": "date", "format": "date_time"},
                        'committer_name': {"type": "string"},
                        'committer_email':{"type": "string", "index": "not_analyzed"},
                        'committer_date': {"type": "date", "format": "date_time"},
                        'message': {"type": "string"},
                        'address': {"type": "string"},
                    }
                },
            }
        })
    print(res)


main()
