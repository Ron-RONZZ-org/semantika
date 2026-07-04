let _entries = $state([]);
let _index = $state(-1);

export const history = {
  get entries() {
    return _entries;
  },

  get index() {
    return _index;
  },

  push(cmd) {
    if (!cmd.trim()) return;
    _entries = [cmd, ..._entries].slice(0, 100);
    _index = -1;
  },

  back() {
    if (_entries.length === 0) return "";
    _index = Math.min(_entries.length - 1, _index + 1);
    return _entries[_index];
  },

  forward() {
    if (_index <= 0) {
      _index = -1;
      return "";
    }
    _index -= 1;
    return _entries[_index];
  },

  reset() {
    _index = -1;
  },
};
