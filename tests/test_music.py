import unittest

from cogs.music import Music


class MusicQueueTests(unittest.TestCase):
    def test_shuffle_queue_keeps_all_tracks(self):
        music = Music(bot=None)
        music.queues[1] = [{"title": str(index)} for index in range(5)]
        before = sorted(track["title"] for track in music.queues[1])

        result = music.shuffle_queue(1)

        self.assertIn("Очередь перемешана", result)
        self.assertEqual(sorted(track["title"] for track in music.queues[1]), before)

    def test_shuffle_queue_requires_two_tracks(self):
        music = Music(bot=None)
        music.queues[1] = [{"title": "only"}]

        self.assertIn("минимум 2", music.shuffle_queue(1))


if __name__ == "__main__":
    unittest.main()
