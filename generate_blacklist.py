#!/usr/bin/env python

'''
Queries ES for ifg config files. Determines if products
 have been generated for configs. If they have not, and
 jobs have failed n times, generate blacklist products.
'''

from __future__ import print_function
import json
import pickle
import hashlib
import requests
from hysds.celery import app
#from requests.auth import HTTPBasicAuth
#from hysds_commons.net_utils import get_container_host_ip

def main():
    '''
    Determines all missing ifgs that have ifgs configs and are
    not blacklisted. Checks those products for failed jobs. If
    those jobs are over the count_to_blacklist, it blacklists
    those products.
    '''
    print('Determining variables & ES products...')
    ctx = load_context()
    ifg_version = ctx['ifg_version']
    count_to_blacklist = ctx['count_to_blacklist']
    ifg_configs = build_hashed_dict(get_ifg_configs(ifg_version))
    ifgs = build_hashed_dict(get_ifgs())
    blacklist = build_hashed_dict(get_blacklist())
    print('Found {} ifg-cfgs, {} ifgs, and {} blacklist products.'.format(len(ifg_configs.keys()), len(ifgs.keys()), len(blacklist.keys())))
    print('Determining missing IFGs...')
    missing = determine_missing_ifgs(ifg_configs, ifgs, blacklist)
    print('Found {} missing IFGs. Checking jobs.')
    add_to_blacklist = determine_failed(missing, count_to_blacklist)
    print('{} jobs have failed {} times or more. Adding each as a blacklist product...'.format(len(add_to_blacklist), count_to_blacklist))
    # placeholder: generate blacklist product from each ifg in new_blacklist


def determine_failed(missing, count_to_blacklist):
    '''
    Determines which ifg-cfg products, which have been filtered by the current
    blacklist, have failed more than count_to_blacklist times. Returns those
    ifg-cfg products. Param missing is the ifg-cfg ES object list.
    '''
    mozart_ip = app.conf['MOZART_ES_URL'].rstrip(':9200').replace('http://', 'https://')
    mozart_url = '{0}/es/grq_*_ifg/_search'.format(mozart_ip)
    es_query = {"query":{"bool":{"must":[{"term":{"job.job_info.job_payload.job_type":"job:job-sciflo-s1-ifg:develop"}}, {"range":{"job.retry_count":{"gte":count_to_blacklist}}}]}}, "from":0, "size":1000}
    all_failed = query_es(mozart_url, es_query)
    add_to_blacklist = []
    for ifg_cfg in missing:
        if is_in(ifg_cfg, all_failed):
            add_to_blacklist.append(ifg_cfg)
    return add_to_blacklist

def is_in(ifg_cfg, failed_job_list):
    '''
    Returns True if the ifg_cfg object is inside the failed_job_list. False otherwise.
    '''
    # PLACEHOLDER
    import random
    return random.randint(0, 1)

def determine_missing_ifgs(ifg_configs, ifgs, blacklist):
    '''
    Determines the ifgs that have not been produced from the ifg configs.
    '''
    ifg_keys = ifgs.keys()
    blacklist_keys = blacklist.keys()
    missing = []
    for key in ifg_configs.keys():
        if not key in ifg_keys and not key in blacklist_keys:
            missing.append(ifg_configs[key])
    return missing

def build_hashed_dict(object_list):
    '''
    Builds a dict of the object list where the keys are a hashed object of each objects
    master and slave list. Returns the dict.
    '''
    hashed_dict = {}
    for obj in object_list:
        hashed_dict.update({gen_hash(obj):obj})
    return hashed_dict

def gen_hash(es_object):
    '''Generates a hash from the master and slave scene list'''
    master = pickle.dumps(sorted(es_object['_source']['metadata']['master_scenes'], -1))
    slave = pickle.dumps(sorted(es_object['_source']['metadata']['slave_scenes'], -1))
    return '{}_{}'.format(hashlib.md5(master).hexdigest(), hashlib.md5(slave).hexdigest())

def get_ifgs():
    '''
    Returns all ifg products on ES
    '''
    grq_ip = app.conf['GRQ_ES_URL'].rstrip(':9200').replace('http://', 'https://')
    grq_url = '{0}/es/grq_*_ifg/_search'.format(grq_ip)
    es_query = {"query":{"bool":{"must":[{"match_all":{}}]}}, "from":0, "size":1000}
    return query_es(grq_url, es_query)

def get_ifg_configs(ifg_version):
    '''Returns all ifg_config products on ES matching the ifg_version'''
    grq_ip = app.conf['GRQ_ES_URL'].rstrip(':9200').replace('http://', 'https://')
    grq_url = '{0}/es/grq_{1}_ifg-cfg/_search'.format(grq_ip, ifg_version)
    es_query = {"query":{"bool":{"must":[{"match_all":{}}]}}, "from":0, "size":1000}
    return query_es(grq_url, es_query)

def get_blacklist():
    '''Returns all blacklist products'''
    grq_ip = app.conf['GRQ_ES_URL'].rstrip(':9200').replace('http://', 'https://')
    grq_url = '{0}/es/grq_*_ifg-blacklist/_search'.format(grq_ip)
    es_query = {"query":{"bool":{"must":[{"match_all":{}}]}}, "from":0, "size":1000}
    return query_es(grq_url, es_query)

def query_es(grq_url, es_query):
    '''
    Runs the query through Elasticsearch, iterates until
    all results are generated, & returns the compiled result
    '''
    # make sure the fields from & size are in the es_query
    if 'size' in es_query.keys():
        iterator_size = es_query['size']
    else:
        iterator_size = 1000
        es_query['size'] = iterator_size
    if 'from' in es_query.keys():
        from_position = es_query['from']
    else:
        from_position = 0
        es_query['from'] = from_position
    # run the query and iterate until all the results have been returned
    response = requests.post(grq_url, data=json.dumps(es_query), timeout=60, verify=False)
    response.raise_for_status()
    results = json.loads(response.text, encoding='ascii')
    results_list = results['hits']['hits']
    total_count = results['hits']['total']
    for i in range(iterator_size, total_count, iterator_size):
        es_query['from'] = i
        response = requests.post(grq_url, data=json.dumps(es_query), timeout=60, verify=False)
        results_list.extend(results['hits']['hits'])
    return results_list

def load_context():
    '''loads the context file into a dict'''
    try:
        context_file = '_context.json'
        with open(context_file, 'r') as fin:
            context = json.load(fin)
        return context
    except:
        raise Exception('unable to parse _context.json from work directory')

if __name__ == '__main__':
    main()
