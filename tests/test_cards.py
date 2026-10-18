"""Reading cards are independent from notes and never invoke a model."""
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cards


class CardTests(unittest.TestCase):
    def test_create_list_and_load_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            card = cards.create(root, {
                'title': '方法直觉 · coronagraph',
                'content': '这里记录一个需要继续理解的术语。',
                'source': '方法拆解',
            }, {'key': 'PAPER', 'title': 'A paper'})
            self.assertEqual(cards.load(root, card['id'])['content'], '这里记录一个需要继续理解的术语。')
            listing = cards.listing(root)
            self.assertEqual(listing['total'], 1)
            self.assertEqual(listing['cards'][0]['paper']['key'], 'PAPER')
            saved = cards.update(root, card['id'], {
                'summary': '这是卡片总结。',
                'conversation': [{'role': 'user', 'content': '它是什么意思？'}, {'role': 'assistant', 'content': '这里是解释。'}],
            })
            self.assertEqual(saved['summary'], '这是卡片总结。')
            self.assertEqual(len(cards.load(root, card['id'])['conversation']), 2)

    def test_empty_card_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                cards.create(Path(directory), {'content': '   '})


if __name__ == '__main__':
    unittest.main()
