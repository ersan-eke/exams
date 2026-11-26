import { createRouter, createWebHistory } from 'vue-router'
import ComingSoonView from '../views/ComingSoonView.vue'

const soon = (path: string, title: string) => ({
  path,
  name: path.slice(1),
  component: ComingSoonView,
  meta: { title },
})

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'new', component: () => import('../views/NewExamView.vue') },
    {
      path: '/exams/:examId/settings',
      name: 'exam-settings',
      component: () => import('../views/ExamSettingsView.vue'),
    },
    {
      path: '/attempts/:attemptId',
      name: 'exam',
      component: () => import('../views/ExamView.vue'),
      meta: { focus: true },
    },
    {
      path: '/attempts/:attemptId/results',
      name: 'results',
      component: () => import('../views/ResultsView.vue'),
    },
    {
      path: '/attempts/:attemptId/grade/:mode(solution|self)',
      name: 'grade',
      component: () => import('../views/GradingView.vue'),
      meta: { focus: true },
    },
    {
      path: '/exams/:examId/view',
      name: 'exam-view',
      component: () => import('../views/ExamPreviewView.vue'),
    },
    { path: '/my-exams', name: 'my-exams', component: () => import('../views/MyExamsView.vue') },
    {
      path: '/statistics',
      name: 'statistics',
      component: () => import('../views/StatisticsView.vue'),
    },
    {
      path: '/statistics/:subject',
      name: 'statistics-subject',
      component: () => import('../views/StatisticsView.vue'),
    },
    soon('/practice', 'Practice'),
    soon('/quizzes', 'Quizzes'),
    { path: '/ask', name: 'ask', component: () => import('../views/AskView.vue') },
    { path: '/study/:subject', name: 'study', component: () => import('../views/StudyView.vue') },
    { path: '/material/:id', name: 'material', component: () => import('../views/MaterialView.vue') },
  ],
})

export default router
