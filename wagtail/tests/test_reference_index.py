from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core import management
from django.test import TestCase

from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, ReferenceIndex
from wagtail.test.testapp.models import (
    EventPage,
    EventPageCarouselItem,
    GenericSnippetNoFieldIndexPage,
    GenericSnippetNoIndexPage,
    GenericSnippetPage,
    ModelWithNullableParentalKey,
)


class TestCreateOrUpdateForObject(TestCase):
    def setUp(self):
        image_model = get_image_model()
        self.image_content_type = ContentType.objects.get_for_model(image_model)

        self.test_feed_image = image_model.objects.create(
            title="Test feed image",
            file=get_test_image_file(),
        )
        self.test_image_1 = image_model.objects.create(
            title="Test image 1",
            file=get_test_image_file(),
        )
        self.test_image_2 = image_model.objects.create(
            title="Test image 2",
            file=get_test_image_file(),
        )

        # Add event page
        self.event_page = EventPage(
            title="Event page",
            slug="event-page",
            location="the moon",
            audience="public",
            cost="free",
            date_from="2001-01-01",
            feed_image=self.test_feed_image,
        )
        self.event_page.carousel_items = [
            EventPageCarouselItem(
                caption="1234567", image=self.test_image_1, sort_order=1
            ),
            EventPageCarouselItem(
                caption="7654321", image=self.test_image_2, sort_order=2
            ),
            EventPageCarouselItem(
                caption="abcdefg", image=self.test_image_1, sort_order=3
            ),
        ]
        self.root_page = Page.objects.get(id=2)
        self.root_page.add_child(instance=self.event_page)

        self.expected_references = {
            (
                self.image_content_type.id,
                str(self.test_feed_image.pk),
                "feed_image",
                "feed_image",
            ),
            (
                self.image_content_type.id,
                str(self.test_image_1.pk),
                "carousel_items.item.image",
                f"carousel_items.{self.event_page.carousel_items.get(sort_order=1).id}.image",
            ),
            (
                self.image_content_type.id,
                str(self.test_image_2.pk),
                "carousel_items.item.image",
                f"carousel_items.{self.event_page.carousel_items.get(sort_order=2).id}.image",
            ),
            (
                self.image_content_type.id,
                str(self.test_image_1.pk),
                "carousel_items.item.image",
                f"carousel_items.{self.event_page.carousel_items.get(sort_order=3).id}.image",
            ),
        }

    def test(self):
        self.assertSetEqual(
            set(
                ReferenceIndex.get_references_for_object(self.event_page).values_list(
                    "to_content_type", "to_object_id", "model_path", "content_path"
                )
            ),
            self.expected_references,
        )

    def test_update(self):
        reference_to_keep = ReferenceIndex.objects.get(
            base_content_type=ReferenceIndex._get_base_content_type(self.event_page),
            content_type=ContentType.objects.get_for_model(self.event_page),
            content_path="feed_image",
        )
        reference_to_remove = ReferenceIndex.objects.create(
            base_content_type=ReferenceIndex._get_base_content_type(self.event_page),
            content_type=ContentType.objects.get_for_model(self.event_page),
            object_id=self.event_page.pk,
            to_content_type=self.image_content_type,
            to_object_id=self.test_image_1.pk,
            model_path="hero_image",  # Field doesn't exist
            content_path="hero_image",
            content_path_hash=ReferenceIndex._get_content_path_hash("hero_image"),
        )

        ReferenceIndex.create_or_update_for_object(self.event_page)

        # Check that the record for the reference to be kept has been preserved/reused
        self.assertTrue(ReferenceIndex.objects.filter(id=reference_to_keep.id).exists())

        # Check that the record for the reference to be removed has been deleted
        self.assertFalse(
            ReferenceIndex.objects.filter(id=reference_to_remove.id).exists()
        )

        # Check that the current stored references are correct
        self.assertSetEqual(
            set(
                ReferenceIndex.get_references_for_object(self.event_page).values_list(
                    "to_content_type", "to_object_id", "model_path", "content_path"
                )
            ),
            {
                (
                    self.image_content_type.id,
                    str(self.test_feed_image.pk),
                    "feed_image",
                    "feed_image",
                ),
                (
                    self.image_content_type.id,
                    str(self.test_image_1.pk),
                    "carousel_items.item.image",
                    f"carousel_items.{self.event_page.carousel_items.get(sort_order=1).id}.image",
                ),
                (
                    self.image_content_type.id,
                    str(self.test_image_2.pk),
                    "carousel_items.item.image",
                    f"carousel_items.{self.event_page.carousel_items.get(sort_order=2).id}.image",
                ),
                (
                    self.image_content_type.id,
                    str(self.test_image_1.pk),
                    "carousel_items.item.image",
                    f"carousel_items.{self.event_page.carousel_items.get(sort_order=3).id}.image",
                ),
            },
        )

    def test_saving_base_model_does_not_remove_references(self):
        page = Page.objects.get(pk=self.event_page.pk)
        page.save()
        self.assertSetEqual(
            set(
                ReferenceIndex.get_references_for_object(self.event_page).values_list(
                    "to_content_type", "to_object_id", "model_path", "content_path"
                )
            ),
            self.expected_references,
        )

    def test_null_parental_key(self):
        obj = ModelWithNullableParentalKey(
            content="""<p><a linktype="page" id="%d">event page</a></p>"""
            % self.event_page.id
        )
        obj.save()

        # Models with a ParentalKey are not considered indexable - references are recorded against the parent model
        # instead. Since the ParentalKey is null here, no reference will be recorded.
        refs = ReferenceIndex.get_references_to(self.event_page)
        self.assertEqual(refs.count(), 0)

    def test_generic_foreign_key(self):
        page1 = GenericSnippetPage(
            title="generic snippet page", snippet_content_object=self.event_page
        )
        self.root_page.add_child(instance=page1)
        page2 = GenericSnippetPage(
            title="generic snippet page", snippet_content_object=None
        )
        self.root_page.add_child(instance=page2)

        refs = ReferenceIndex.get_references_to(self.event_page)
        self.assertEqual(refs.count(), 1)

    def test_model_index_ignore_generic_foreign_key(self):
        page1 = GenericSnippetNoIndexPage(
            title="generic snippet page", snippet_content_object=self.event_page
        )
        self.root_page.add_child(instance=page1)
        page2 = GenericSnippetNoIndexPage(
            title="generic snippet page", snippet_content_object=None
        )
        self.root_page.add_child(instance=page2)

        # There should be no references
        refs = ReferenceIndex.get_references_to(self.event_page)
        self.assertEqual(refs.count(), 0)

    def test_model_field_index_ignore_generic_foreign_key(self):
        content_type = ContentType.objects.get_for_model(self.event_page)
        page1 = GenericSnippetNoFieldIndexPage(
            title="generic snippet page", snippet_content_type_nonindexed=content_type
        )
        self.root_page.add_child(instance=page1)
        page2 = GenericSnippetNoFieldIndexPage(
            title="generic snippet page", snippet_content_type_nonindexed=None
        )
        self.root_page.add_child(instance=page2)

        # There should be no references
        refs = ReferenceIndex.get_references_to(content_type)
        self.assertEqual(refs.count(), 0)

    def test_rebuild_references_index_no_verbosity(self):
        stdout = StringIO()
        management.call_command(
            "rebuild_references_index",
            verbosity=0,
            stdout=stdout,
        )
        self.assertFalse(stdout.read())
