# GEN-192

Some code/files used to investigate a bug in `runGenRAPerfPred` endpoint for GEN-192.

Running `python3 perfpred.py` from this directory will allow you to make some pre-formatted requests:
- POST to runGenRAPerfPred
- GET to uiRunGeneratedRunAcross
in either the NCD endpoint or local deployment of GenRA.

Upon receiving a response, it will enter a pdb debugger mode. 
In the debugger mode, play with the `resp` python variable to inspect request/response in detail.

Once you type and enter `q`, the debugger mode will quit to take you to another round of request.

If you wish to quit the program, `ctrl` + `c` when you're not in pdb mode.

If you wish to add more pre-formatted requests, follow the format outlined in `perfpred.py`.

Lastly, if you wish to use a pre-formatted POST to runGenRAPerfPred via curl, use `curl_post_runGenRAPerfPred.sh`.
