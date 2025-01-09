import unittest
import json
from unittest.mock import patch, MagicMock
from service import app

class TestWeiboAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_refresh_weibo(self):
        # 测试有效的请求
        response = self.app.post('/refresh', 
            json={'user_id_list': ['1234567890']},
            content_type='application/json')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 202)
        self.assertTrue('task_id' in data)
        self.assertEqual(data['status'], 'Task started')
        self.assertEqual(data['user_id_list'], ['1234567890'])

    def test_refresh_weibo_invalid_params(self):
        # 测试无效的请求参数
        response = self.app.post('/refresh', 
            json={'user_id_list': 'invalid'},
            content_type='application/json')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 400)
        self.assertTrue('error' in data)

    def test_refresh_weibo_no_params(self):
        # 测试缺少参数
        response = self.app.post('/refresh')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 400)
        self.assertTrue('error' in data)

    @patch('service.tasks')
    def test_get_task_status(self, mock_tasks):
        # 模拟任务状态
        mock_tasks.get.return_value = {
            'state': 'PROGRESS',
            'progress': 50
        }
        
        response = self.app.get('/task/test_task_id')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['state'], 'PROGRESS')
        self.assertEqual(data['progress'], 50)

    def test_get_nonexistent_task(self):
        response = self.app.get('/task/nonexistent_id')
        self.assertEqual(response.status_code, 404)

    @patch('sqlite3.connect')
    def test_get_weibos(self, mock_connect):
        # 模拟数据库返回结果
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, '测试微博1', '2023-01-01'),
            (2, '测试微博2', '2023-01-02')
        ]
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        response = self.app.get('/weibos')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data), 2)

    @patch('sqlite3.connect')
    def test_get_weibo_detail(self, mock_connect):
        # 模拟数据库返回结果
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, '测试微博1', '2023-01-01')
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        response = self.app.get('/weibos/1')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data), 3)

    @patch('sqlite3.connect')
    def test_get_nonexistent_weibo(self, mock_connect):
        # 模拟数据库返回空结果
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_connect.return_value.cursor.return_value = mock_cursor
        
        response = self.app.get('/weibos/999')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(data['error'], 'Weibo not found')

    @patch('sqlite3.connect')
    def test_database_error(self, mock_connect):
        # 模拟数据库连接错误
        mock_connect.side_effect = Exception('Database connection error')
        
        response = self.app.get('/weibos')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 500)
        self.assertTrue('error' in data)

    @patch('service.get_running_task')
    def test_refresh_with_running_task(self, mock_get_running_task):
        # 模拟已有运行中的任务
        mock_get_running_task.return_value = ('existing_task_id', {
            'state': 'PROGRESS',
            'progress': 50,
            'user_id_list': ['1234567890']
        })
        
        response = self.app.post('/refresh', 
            json={'user_id_list': ['9876543210']},
            content_type='application/json')
        data = json.loads(response.data.decode())
        
        self.assertEqual(response.status_code, 409)
        self.assertEqual(data['task_id'], 'existing_task_id')
        self.assertEqual(data['status'], 'Task already running')

if __name__ == '__main__':
    unittest.main()