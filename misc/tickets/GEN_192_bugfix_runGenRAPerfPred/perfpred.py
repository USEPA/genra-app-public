import json
import requests
import pdb

'''
run with `python3 perfpred.py`.

You can add files from `tests/data/comparison_0/data` or any others that follow json format described in readme in that directory.

If so, make sure filename `sample<#>.json`, and add to `fname_dict` below.

If you want to quit, you'll first have to exit pdb.
'''


fname_dict = {
	'a': "sample.json",
	'b': "sample2.json",
	'c': "request_body",
	'd': "expected_rgra_DTXCID30182.json"
}

url_dict = {
	'a': "https://comptox.epa.gov/dashboard/genra/api/genra/v3",
	'b': "http://127.0.0.1:31002/api/genra/v3"
}

other_params = "&k0=10&s0=0.1&pos0=1&neg0=1&fp=chm_mrgn&sel_by=tox_txrf"

def print_select(d):
	[print(key, value) for key, value in d.items()]
	key = input("\nchoose input: \n")
	return d[key]

def make_request(fname, url):

	with open(fname, 'r') as f:
		data = json.load(f)

	if 'expected_' in fname:
		return requests.get(url + "/uiRunGeneratedRunAcross/?dsstox_cid=" + fname.split('_')[-1][:-5] + other_params)

	else:		

		if 'sample' in fname:
			post_json = data['runGenRAPerfPred']['request_body']
		elif 'request_body' in fname:
			post_json = data
		else:
			post_json = None

		return requests.post(
			url + '/runGenRAPerfPred',
			json=post_json,
			headers={
				'Content-type': 'application/json',
				'Accept': '*/*'
			}
		)



while (True):
	fname = print_select(fname_dict)
	url = print_select(url_dict)


	resp = make_request(fname, url)

	try:
		pdb.set_trace()
		z=1
	except:
		pass

