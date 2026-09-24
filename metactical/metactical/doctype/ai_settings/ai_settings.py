# Copyright (c) 2026, Storebuilder Commerce Inc and contributors
# For license information, please see license.txt
"""Where the AI provider, model and key live, for every feature in this app that asks one.

One Single rather than a copy per feature: the key and the model are the things that change, and
they change for all of them at once. What each feature *asks* stays with the feature.
"""
import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class NotConfigured(Exception):
	"""Raised, never thrown: every caller has a fallback and has to be able to catch this."""


class AISettings(Document):
	def validate(self):
		self.base_url = (self.base_url or "").strip().rstrip("/")
		self.model = (self.model or "").strip()

	def check_ready(self):
		if not self.enabled:
			raise NotConfigured("AI Settings is switched off")
		if not self.base_url:
			raise NotConfigured("AI Settings has no base URL")
		if not self.model:
			raise NotConfigured("AI Settings has no model")
		if not self.get_password("api_key", raise_exception=False):
			raise NotConfigured("AI Settings has no API key")

	def key(self):
		return self.get_password("api_key", raise_exception=False)

	def price(self, prompt_tokens, completion_tokens):
		"""What the call cost, in USD, at the rates on this Single."""
		return (cint(prompt_tokens) * flt(self.input_cost_per_million)
				+ cint(completion_tokens) * flt(self.output_cost_per_million)) / 1_000_000.0


def get_settings():
	return frappe.get_cached_doc("AI Settings")
