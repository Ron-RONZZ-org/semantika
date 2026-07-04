const DEFAULT_DURATION = 3000;

let _message = $state("");
let _type = $state("success");
let _visible = $state(false);
let _timer = null;

function _clearTimer() {
  if (_timer) {
    clearTimeout(_timer);
    _timer = null;
  }
}

export const banner = {
  get message() { return _message; },
  get type() { return _type; },
  get visible() { return _visible; },

  show(message, type = "success", duration = DEFAULT_DURATION) {
    _clearTimer();
    _message = message;
    _type = type;
    _visible = true;
    _timer = setTimeout(() => {
      _visible = false;
      _message = "";
    }, duration);
  },

  dismiss() {
    _clearTimer();
    _visible = false;
    _message = "";
  },
};
