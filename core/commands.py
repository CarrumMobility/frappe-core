import click
import frappe
from frappe.commands import pass_context

from core.services.util_service import publish_docs as publish_docs_to_website


@click.command("publish-docs")
@pass_context
def publish_docs(context):
	"""Publish markdown docs from core/docs as website pages at /docs/{category}/{file_name}."""
	for site in context.sites:
		frappe.init(site=site)
		frappe.connect()

		result = publish_docs_to_website()
		for item in result["published"]:
			click.echo(f"{item['action'].title()}: {item['file']} -> /{item['route']}")
		click.secho(
			f"Site {site}: {result['created']} created, {result['updated']} updated",
			fg="green",
		)
		frappe.destroy()


commands = [publish_docs]
