from flask import Flask, render_template, Response, request
import os
import datetime
import json
import pymongo
import calendar
import pandas as pd

app = Flask(__name__)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))   # refers to application_top
APP_STATIC = os.path.join(APP_ROOT, 'static')

mongo_client = pymongo.MongoClient('172.16.4.51', 27017)

month_calendar = dict((v,k) for k,v in enumerate(calendar.month_abbr))
disease_collection = {'articles': {'zika': 'articles',
                                   'mers': 'mers',
                                   'mayaro': 'mayaro',
                                   'oropouche': 'oropouche'},
                      'citations': {'zika': 'citations',
                                    'mers': 'citations_mers',
                                    'mayaro': 'citations_mayaro',
                                    'oropouche': 'citations_oropouche'}}


def fix_abstract(art):
    if 'Abstract' not in art['MedlineCitation']['Article'] or art['MedlineCitation']['Article']['Abstract'] == "":
        art['MedlineCitation']['Article']['Abstract'] = {'AbstractText':  " "}
    else:
        art['MedlineCitation']['Article']['Abstract']['AbstractText'] = art['MedlineCitation']['Article']['Abstract']['AbstractText'][0]

    return art


def get_link(art):
    article_id_list = art['PubmedData']['ArticleIdList']
    article_id_list.sort(key=len)

    if '/' in article_id_list[-1]:
        art['link'] = 'https://doi.org/'+article_id_list[-1]
    else:
        art['link'] = None
    return art

@app.route("/")
@app.route("/<virus>")
def root(virus="zika"):
    return render_template('pages/indextimeline.html')

@app.route('/api/citations')
def json_bundle():
    col_cit = mongo_client.pubmed.citations
    col_art = mongo_client.pubmed.articles
    citations_dict = {}

    citations = col_cit.find()
    for relation in citations:
        article = col_art.find_one({'MedlineCitation.PMID': relation['PMID']})

        if article is None:
            continue

        citedby = []
        for cited in relation['citedby']:
            exists = col_art.find_one({'MedlineCitation.PMID': cited})
            if exists is not None:
                citedby.append(cited)

        date = article['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']
        citations_dict[relation['PMID']] = {'title': article['MedlineCitation']['Article']['ArticleTitle'],
                                            'citedby': citedby,
                                            'year': date.get('Year', None),
                                            'link': get_link(article)['link']}

    return json.dumps(citations_dict), 200

@app.route('/api/timeseries')
def json_tseries():
    disease = request.args.get('disease')
    search = request.args.get('search')
    col_art = mongo_client['pubmed']['articles']

    if not search:
        query = {}
    else:
        query = {"$text": {"$search": search}}


    articles = col_art.find(query,
                            {'MedlineCitation.Article.Journal.JournalIssue.PubDate': 1,
                             'MedlineCitation.Article.ArticleTitle': 1})
    dates_list = []
    for article in articles:
        date = article['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']
        if 'Year' in date:
            dates_list.append({'date': datetime.date(int(date['Year']),
                                                     month_calendar[date.get('Month', 'Jan')],
                                                     int(date.get('Day', 1))),
                               'count': 1})
    df = pd.DataFrame(dates_list)
    df = df.set_index(pd.DatetimeIndex(df['date']))
    df = df['date'].resample('A', how='count')
    return df.to_json(date_format='iso')


@app.route('/api/publications')
def json_timeline():
    disease = request.args.get('disease')
    search = request.args.get('search')
    col = mongo_client['pubmed']['articles']

    if not search:
        query = {}
    else:
        query = {"$text": {"$search": search}}

    articles = list(col.find(query))

    valid_articles = []
    for art in articles:
        date = art['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']
        if 'Year' in date:
            art = fix_abstract(art)
            art['PubDatetime'] = {'Year': int(date['Year']),
                                  'Month': month_calendar[date.get('Month', 'Jan')],
                                  'Day': int(date.get('Day', 1))}

            art = get_link(art)
            valid_articles.append(art)

    dados = render_template('pages/timeline.json', busca='Zika Virus', articles=valid_articles)
    return Response(dados, mimetype='application/json')

@app.errorhandler(500)
def page_not_found(e):
    return e, 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=True)


