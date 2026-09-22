"""The one place this app talks to an AI provider.

Every call goes through `ask_json` and every call leaves an **AI Request Log** row - the request,
the response and the token spend in one record. Nothing here decides anything about the catalogue;
it asks a question and hands back the parsed answer.

**Failure is a return value, not an exception.** `ask_json` raises only `AIUnavailable`, and every
caller is expected to catch it and carry on with whatever it did before. An AI that is down must
never be the reason a merge screen cannot open.

**Cost.** The prompts here are small and the answers are JSON, so the spend is dominated by how
many times this is called rather than by any single call. Callers batch (see
`max_items_per_request`), send the shortest form of every value, and pin `temperature=0` so the
same family asked twice gives the same answer.
"""
import json
import time

import frappe
import requests

from metactical.metactical.doctype.ai_settings.ai_settings import NotConfigured, get_settings

LOG_DOCTYPE = "AI Request Log"
CONNECT_TIMEOUT = 5

# A logged request or response is for a person to read, not a payload to replay. Truncate rather
# than let one runaway answer put a megabyte in the database.
MAX_LOGGED = 60_000


class AIUnavailable(Exception):
	"""The provider could not answer. Carries a sentence fit to show an operator."""


def _clip(text):
	text = text if isinstance(text, str) else json.dumps(text, indent=1, default=str)
	return text if len(text) <= MAX_LOGGED else text[:MAX_LOGGED] + "\n... truncated"


def _log(feature, reference, settings, payload, response, usage, started, error=None):
	"""Write the row. Never lets a logging problem become the caller's problem."""
	try:
		usage = usage or {}
		prompt = int(usage.get("prompt_tokens") or 0)
		completion = int(usage.get("completion_tokens") or 0)
		frappe.get_doc({
			"doctype": LOG_DOCTYPE,
			"feature": feature,
			"reference": reference,
			"status": "Failed" if error else "Success",
			"provider": (settings.provider if settings else None) or "OpenAI",
			"model": (settings.model if settings else None),
			"duration_ms": int((time.monotonic() - started) * 1000),
			"prompt_tokens": prompt,
			"completion_tokens": completion,
			"total_tokens": int(usage.get("total_tokens") or (prompt + completion)),
			"cost_usd": settings.price(prompt, completion) if settings else 0,
			"request": _clip(payload),
			"response": _clip(response),
			"error": (error or "")[:1000] or None,
		}).insert(ignore_permissions=True)
		# The log has to survive whatever the caller does next, including a rollback, or a failed
		# run leaves no trace of the call that caused it. But a commit here would also make
		# permanent whatever else the caller has pending, so it only commits when the log row is
		# the only thing in the transaction. Callers today are read paths, so it always is.
		if frappe.db.transaction_writes <= 1:
			frappe.db.commit()
	except Exception:
		frappe.log_error(title="AI Request Log", message=frappe.get_traceback())


def ask_json(feature, system, user, reference=None, max_output_tokens=None):
	"""Ask for one JSON object. Returns the parsed dict, or raises AIUnavailable.

	`response_format=json_object` is what keeps this cheap: no prose to pay for, no fence to strip,
	and a malformed answer is the provider's error rather than something to parse around.
	"""
	started = time.monotonic()
	try:
		settings = get_settings()
		settings.check_ready()
	except NotConfigured as e:
		raise AIUnavailable(str(e)) from None
	except Exception as e:
		raise AIUnavailable("AI Settings could not be read: {0}".format(e)) from None

	payload = {
		"model": settings.model,
		"temperature": 0,
		"response_format": {"type": "json_object"},
		"max_tokens": int(max_output_tokens or settings.max_output_tokens or 4096),
		"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
	}
	url = "{0}/chat/completions".format(settings.base_url)
	headers = {"Content-Type": "application/json",
			   "Authorization": "Bearer {0}".format(settings.key())}

	try:
		response = requests.post(url, json=payload, headers=headers,
								 timeout=(CONNECT_TIMEOUT, int(settings.timeout or 60)))
	except Exception as e:
		_log(feature, reference, settings, payload, None, None, started,
			 error="could not reach {0}: {1}".format(url, e))
		raise AIUnavailable("could not reach the AI provider ({0})".format(str(e)[:120])) from None

	try:
		body = response.json()
	except ValueError:
		body = {"raw": response.text[:2000]}

	if response.status_code != 200:
		message = ((body.get("error") or {}).get("message")
				   if isinstance(body.get("error"), dict) else None)
		note = "the AI provider returned HTTP {0}{1}".format(
			response.status_code, ": " + message[:160] if message else "")
		_log(feature, reference, settings, payload, body, body.get("usage"), started, error=note)
		raise AIUnavailable(note)

	usage = body.get("usage") or {}
	choice = (body.get("choices") or [{}])[0]

	# A reply cut off at max_tokens is half a JSON object. Discarding it is the only safe move -
	# parsing what arrived would quietly drop whatever did not.
	if choice.get("finish_reason") == "length":
		note = ("the answer was cut off at {0} tokens - lower Max Items Per Request or raise Max "
				"Output Tokens on AI Settings".format(payload["max_tokens"]))
		_log(feature, reference, settings, payload, body, usage, started, error=note)
		raise AIUnavailable(note)

	content = ((choice.get("message") or {}).get("content") or "").strip()
	try:
		parsed = json.loads(content)
		if not isinstance(parsed, dict):
			raise ValueError("not an object")
	except ValueError:
		note = "the AI provider sent back something that is not a JSON object"
		_log(feature, reference, settings, payload, body, usage, started, error=note)
		raise AIUnavailable(note) from None

	_log(feature, reference, settings, payload, body, usage, started)
	return parsed


def is_enabled():
	"""Whether a call is worth attempting at all - so a caller can skip the round trip."""
	try:
		settings = get_settings()
		settings.check_ready()
		return True
	except Exception:
		return False
