from django_migration_testcase import MigrationTest


class SitePageQuestionMigrationTest(MigrationTest):
    app_name = "wizard_builder"
    before = "0048_formquestion_sites"
    after = "0049_copy_sites_from_page_to_question"

    def migrate_kwargs(self):
        return {"verbosity": 1, "interactive": False}

    def test_site_populated(self):
        FormQuestion = self.get_model_before("wizard_builder.FormQuestion")
        Page = self.get_model_before("wizard_builder.Page")

        page = Page.objects.create()
        page.sites.add(1)
        question = FormQuestion.objects.create(page=page)
        FormQuestion.objects.create(page=page)

        for question in FormQuestion.objects.all():
            self.assertFalse(question.sites.count())

        self.run_migration()
        FormQuestion = self.get_model_after("wizard_builder.FormQuestion")

        for question in FormQuestion.objects.all():
            self.assertTrue(question.sites.count())
