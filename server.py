#!/usr/bin/env python

import argparse
import connexion
import os
import re
import time
import yaml
from flask import send_from_directory, redirect, request, jsonify
from flask_cors import CORS

from selenium import webdriver
from bs4 import BeautifulSoup

# from backend.Project import Project # TODO !!
from backend import AVAILABLE_MODELS

__author__ = 'Hendrik Strobelt, Sebastian Gehrmann'

CONFIG_FILE_NAME = 'lmf.yml'
projects = {}

app = connexion.App(__name__, debug=False)


class Project:
    def __init__(self, LM, config):
        self.config = config
        self.lm = LM()


def get_all_projects():
    res = {}
    for k in projects.keys():
        res[k] = projects[k].config
    return res


def analyze(analyze_request):
    project = analyze_request.get('project')
    text = analyze_request.get('text')

    res = {}
    if project in projects:
        p = projects[project] # type: Project
        res = p.lm.check_probabilities(text, topk=20)

    return {
        "request": {'project': project, 'text': text},
        "result": res
    }


def clean_html(raw_html):
  cleanr = re.compile('<.*?>')
  cleantext = re.sub(cleanr, '', raw_html)
  return cleantext

dp = {}

@app.route('/get_article_contents', methods=['GET', 'POST'])
def get_article_contents():
    start = time.time()

    data = request.get_json()
    url = data['url']

    if url in dp:
        print("already in DP")
        return jsonify({
            "content": dp[url]
        })

    options = webdriver.ChromeOptions()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--incognito')
    options.add_argument('--headless')

    driver = webdriver.Chrome("/usr/lib/chromium-browser/chromedriver", chrome_options=options)
    driver.get(url)
    time.sleep(0.1)

    page_source = driver.page_source

    soup = BeautifulSoup(page_source, 'html.parser')

    content = ""
    for par in soup.find_all('p'):
        content += ' '.join(str(par).split()[1:-1])

    driver.quit()

    content = clean_html(content)

    print(content)
    print("time", time.time() - start)

    dp[url] = content
    return jsonify({
        "content": content
    })

TOPK = 10

@app.route('/analyze_text', methods=['GET', 'POST'])
def analyze_text():
    data = request.get_json()
    print(data, projects)

    project = data['project']
    text = data['text']

    res = {}
    if project in projects:
        p = projects[project] # type: Project
        res = p.lm.check_probabilities(text, topk=TOPK)

    print(text, project)

    if len(res['bpe_strings'][1:]) == 0:
        return jsonify({
            "request": {'project': project, 'text': text},
            # "result": res,
            "regularity": 0.0
        })

    topk_cnt = 0
    for i, bpe_string in enumerate(res['bpe_strings'][1:]):
        for j in range(TOPK):
            if res['pred_topk'][i][j][0] == bpe_string:
                topk_cnt += 1
                break

    return jsonify({
        "request": {'project': project, 'text': text},
        # "result": res,
        "regularity": 1.0 * topk_cnt / len(res['bpe_strings'][1:])
    })



#########################
#  some non-logic routes
#########################


@app.route('/')
def redir():
    return redirect('client/index.html')


@app.route('/client/<path:path>')
def send_static(path):
    """ serves all files from ./client/ to ``/client/<path:path>``

    :param path: path from api call
    """
    return send_from_directory('client/dist/', path)


@app.route('/data/<path:path>')
def send_data(path):
    """ serves all files from the data dir to ``/data/<path:path>``

    :param path: path from api call
    """
    print('Got the data route for', path)
    return send_from_directory(args.dir, path)


# @app.route('/')
# def redirect_home():
#     return redirect('/client/index.html', code=302)


# def load_projects(directory):
#     """
#     searches for CONFIG_FILE_NAME in all subdirectories of directory
#     and creates data handlers for all of them
#
#     :param directory: scan directory
#     :return: null
#     """
#     project_dirs = []
#     for root, dirs, files in walklevel(directory, level=2):
#         if CONFIG_FILE_NAME in files:
#             project_dirs.append(root)
#
#     i = 0
#     for p_dir in project_dirs:
#         with open(os.path.join(p_dir, CONFIG_FILE_NAME), 'r') as yf:
#             config = yaml.load(yf)
#             dh_id = os.path.split(p_dir)[1]
#             projects[dh_id] = Project(config=config, project_dir=p_dir,
#                                       path_url='data/' + os.path.relpath(p_dir,
#                                                                          directory))
#         i += 1
#
#
# # https://stackoverflow.com/a/234329/265298
# def walklevel(some_dir, level=1):
#     some_dir = some_dir.rstrip(os.path.sep)
#     assert os.path.isdir(some_dir)
#     num_sep = some_dir.count(os.path.sep)
#     for root, dirs, files in os.walk(some_dir):
#         yield root, dirs, files
#         num_sep_this = root.count(os.path.sep)
#         if num_sep + level <= num_sep_this:
#             del dirs[:]


app.add_api('server.yaml')

parser = argparse.ArgumentParser()
parser.add_argument("--model", default='gpt-2-small')
parser.add_argument("--nodebug", default=True)
parser.add_argument("--address",
                    default="127.0.0.1")  # 0.0.0.0 for nonlocal use
parser.add_argument("--port", default="5001")
parser.add_argument("--nocache", default=False)
parser.add_argument("--dir", type=str, default=os.path.abspath('data'))

parser.add_argument("--no_cors", action='store_true')

if __name__ == '__main__':
    args = parser.parse_args()

    if not args.no_cors:
        CORS(app.app, headers='Content-Type')


    try:
        model = AVAILABLE_MODELS[args.model]
    except KeyError:
        print("Model {} not found. Make sure to register it.".format(
            args.model))
        print("Loading GPT-2 instead.")
        model = AVAILABLE_MODELS['gpt-2']
    projects[args.model] = Project(model, args.model)


    app.run(port=int(args.port), debug=not args.nodebug, host=args.address)
else:
    args, _ = parser.parse_known_args()
    # load_projects(args.dir)
    try:
        model = AVAILABLE_MODELS[args.model]
    except KeyError:
        print("Model {} not found. Make sure to register it.".format(
            args.model))
        print("Loading GPT-2 instead.")
        model = AVAILABLE_MODELS['gpt-2']
    projects[args.model] = Project(model, args.model)
