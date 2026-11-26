export interface BBox {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface Region {
  page: number
  bbox: BBox
  image: string | null
  /** the crop says more than the text (figure, table, formula, code); missing on older exams = true */
  visual?: boolean | null
}

export interface McOption {
  region: number
  /** relative 0..1 inside that region's image */
  bbox: BBox
  text: string
}

export interface AnswerBox {
  region: number
  /** relative 0..1 inside that region's image */
  bbox: BBox
}

export interface Subtask {
  id: string
  label: string
  points: number | null
  independent: boolean
  regions: Region[]
  text: string
  solution_text: string
  mc_options?: McOption[]
  mc_key?: number[] | null
  /** the printed answer areas, at most one per region; a text field goes on each */
  answer_boxes?: AnswerBox[]
}

export interface Context {
  id: string
  applies_from: string | null
  regions: Region[]
  text: string
}

export interface Task {
  id: string
  number: string
  title: string
  points: number | null
  context: Context[]
  subtasks: Subtask[]
  /** MC rule stated in the task's intro; wins over the attempt's (exam-wide) rule */
  mc_rule?: McRule | null
}

export type McRule =
  | { kind: 'all_or_nothing' }
  | { kind: 'per_tick'; right: number; wrong: number; floor: number; single?: number | null }

export interface Issue {
  level: 'warn' | 'error'
  message: string
}

export interface ExamStructure {
  source: string
  page_count: number
  page_sizes: [number, number][]
  kind: 'digital' | 'scanned' | 'mixed'
  is_solution: boolean
  total_points_stated: number | null
  tasks: Task[]
  issues: Issue[]
  duration_minutes?: number | null
  mc_rule?: McRule | null
}
