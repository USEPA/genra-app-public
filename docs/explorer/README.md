This is the source for the help text for the (i) icon for the
nearest neighbor explorer graph pop-up.

The source is [`explorer.md`](./explorer.md), which is converted
with

    docker run -u $(id -u) -v $PWD:/data pandoc/core \
      --standalone --embed-resources --metadata pagetitle="title" \
      explorer.md -o explorer.html
    sed -i -n -e '/^<body>$/,/^<.body>$/{//!p}' explorer.html

which handles `<img src="data::image/png;base64, iVBOR...` for us.
HTML needs to be edited to just include `body` *content*, which the `sed`
command does.

The output ([explorer.html](./explorer.html)) needs to be tracked in the
genra_app repo. as it's pulled in by the `uiSetup` endpoint.
