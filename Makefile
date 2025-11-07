.PHONY: webhook_set webhook_delete

webhook_set:
	python -m app.webhook set

webhook_delete:
	python -m app.webhook delete
