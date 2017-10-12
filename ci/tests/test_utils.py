import pytz

from datetime import datetime

from django.test import TestCase

from .. import utils


class UtilsTests(TestCase):

    def test_transform_timeseries_data(self):
        ts = {
            u'subscriptions.created.sum': [
                {'x': 1483297200000, 'y': 9.0},
                {'x': 1483300800000, 'y': 5.0},
                {'x': 1483304400000, 'y': 1.0},
                {'x': 1483308000000, 'y': 1.0},
                {'x': 1483311600000, 'y': 1.0},
                {'x': 1483315200000, 'y': 1.0},
                {'x': 1483318800000, 'y': 0.0},
                {'x': 1483322400000, 'y': 0.0},
                {'x': 1483326000000, 'y': 2.0},
                {'x': 1483329600000, 'y': 1.0},
                {'x': 1483333200000, 'y': 3.0},
                {'x': 1483336800000, 'y': 10.0},
                {'x': 1483340400000, 'y': 22.0},
                {'x': 1483344000000, 'y': 143.0},
                {'x': 1483347600000, 'y': 102.0},
                {'x': 1483351200000, 'y': 86.0},
                {'x': 1483354800000, 'y': 86.0},
                {'x': 1483358400000, 'y': 91.0},
                {'x': 1483362000000, 'y': 87.0},
                {'x': 1483365600000, 'y': 91.0},
                {'x': 1483369200000, 'y': 107.0},
                {'x': 1483372800000, 'y': 109.0},
                {'x': 1483376400000, 'y': 137.0},
                {'x': 1483380000000, 'y': 626.0},
                {'x': 1483383600000, 'y': 43.0},
                {'x': 1483387200000, 'y': 24.0},
                {'x': 1483390800000, 'y': 15.0},
                {'x': 1483394400000, 'y': 3.0},
                {'x': 1483398000000, 'y': 0.0},
                {'x': 1483401600000, 'y': 2.0},
                {'x': 1483405200000, 'y': 1.0},
                {'x': 1483408800000, 'y': 1.0},
                {'x': 1483412400000, 'y': 5.0},
                {'x': 1483416000000, 'y': 4.0},
                {'x': 1483419600000, 'y': 23.0},
                {'x': 1483423200000, 'y': 13.0}
            ]
        }

        # Test start only
        r1 = utils.transform_timeseries_data(ts, 1483308000000)
        self.assertEqual(len(r1), 33)

        # Test start and end
        r2 = utils.transform_timeseries_data(ts, 1483308000000, 1483326000000)
        self.assertEqual(len(r2), 6)

        # Test data format
        self.assertEqual(r2, [1.0, 1.0, 1.0, 0.0, 0.0, 2.0])

    def test_get_last_value_from_timeseries(self):
        ts = {
            'subscriptions.send.estimate.1.last': [
                {'x': 1482796800000, 'y': 2538.0},
                {'x': 1482883200000, 'y': 2515.0},
                {'x': 1482969600000, 'y': 2542.0},
                {'x': 1483056000000, 'y': 2532.0}
            ]
        }

        r1 = utils.get_last_value_from_timeseries(ts)
        self.assertEqual(r1, 2532.0)

        r2 = utils.get_last_value_from_timeseries({})
        self.assertEqual(r2, 0)

    def test_week_from_datetime(self):
        tz = pytz.timezone('Africa/Johannesburg')
        utc = pytz.timezone('UTC')
        d1 = tz.localize(datetime(2016, 12, 5, 8, 15, 0, 0))
        r1 = utils.DTBoundry.week_from_datetime(d1)
        self.assertIsInstance(r1, utils.DTBoundry)
        self.assertEqual(
            r1.start,
            utc.localize(datetime(2016, 12, 5, 0, 0, 0, 0))
        )
        self.assertEqual(
            r1.end,
            utc.localize(datetime(2016, 12, 11, 0, 0, 0, 0))
        )

    def test_day_from_datetime(self):
        tz = pytz.timezone('Africa/Johannesburg')
        utc = pytz.timezone('UTC')
        d1 = tz.localize(datetime(2016, 12, 5, 8, 15, 0, 0))
        r1 = utils.DTBoundry.day_from_datetime(d1)
        self.assertIsInstance(r1, utils.DTBoundry)
        self.assertEqual(
            r1.start,
            utc.localize(datetime(2016, 12, 4, 22, 0, 0, 0))
        )
        self.assertEqual(
            r1.end,
            utc.localize(datetime(2016, 12, 5, 21, 0, 0, 0))
        )

    def test_validate_page_number(self):
        """
        Ensures that it is a valid int, and that it is greater than 1.
        """
        self.assertRaises(
            utils.PageNotAnInteger, utils.validate_page_number, 'a')
        self.assertRaises(
            utils.EmptyPage, utils.validate_page_number, 0)
        self.assertEqual(utils.validate_page_number('3'), 3)

    def test_no_count_page(self):
        """
        Replicates the same API as a django page object.
        """
        page = utils.NoCountPage(['a', 'b'], 2, 2, True)
        self.assertEqual(str(page), "<Page 2>")
        self.assertEqual(page.has_next(), True)
        self.assertEqual(page.next_page_number(), 3)
        self.assertEqual(page.previous_page_number(), 1)
        self.assertRaises(NotImplementedError, page.start_index)
        self.assertRaises(NotImplementedError, page.end_index)
        self.assertEqual(list(page), ['a', 'b'])

    def test_get_page_of_iterator_has_next(self):
        """
        If the iterator has more values, has_next is true.
        """
        iterator = (i for i in range(10))
        page = utils.get_page_of_iterator(iterator, 5, 1)
        self.assertEqual(list(page), [0, 1, 2, 3, 4])
        self.assertEqual(page.has_next(), True)

    def test_get_page_of_iterator_last_page(self):
        """
        If the iterator has more values, has_next is true.
        """
        iterator = (i for i in range(10))
        page = utils.get_page_of_iterator(iterator, 5, 2)
        self.assertEqual(list(page), [5, 6, 7, 8, 9])
        self.assertEqual(page.has_next(), False)

    def test_get_page_of_iterator(self):
        """
        Defaults to first page if any issues.
        """
        iterator = (i for i in range(10))
        page = utils.get_page_of_iterator(iterator, 5, 'a')
        self.assertEqual(page.number, 1)
        self.assertEqual(list(page), [0, 1, 2, 3, 4])

        iterator = (i for i in range(10))
        page = utils.get_page_of_iterator(iterator, 5, -1)
        self.assertEqual(page.number, 1)
        self.assertEqual(list(page), [0, 1, 2, 3, 4])

        iterator = (i for i in range(10))
        page = utils.get_page_of_iterator(iterator, 5, 100)
        self.assertEqual(page.number, 1)
        self.assertEqual(list(page), [0, 1, 2, 3, 4])
