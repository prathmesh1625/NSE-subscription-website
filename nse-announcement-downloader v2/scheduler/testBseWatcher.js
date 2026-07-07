const watcher =
    require("./bseWatcher");

watcher()
    .then(() => process.exit(0))
    .catch(console.error);