import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "",
});

export interface Repo {
  id: number;
  full_name: string;
  installed_at: string;
}

export interface ReviewSummary {
  id: number;
  pr_number: number;
  pr_title: string;
  author: string;
  status: string;
  created_at: string;
  issue_count: number;
}

export interface ReviewComment {
  id: number;
  file_path: string;
  line_number: number;
  category: string;
  severity: string;
  comment: string;
  suggestion: string | null;
}

export interface ReviewDetail {
  id: number;
  pr_number: number;
  pr_title: string;
  author: string;
  status: string;
  created_at: string;
  comments: ReviewComment[];
}

export interface TrendPoint {
  review_id: number;
  pr_number: number;
  created_at: string;
  by_severity: Record<string, number>;
}

export interface Metrics {
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  total: number;
  trend: TrendPoint[];
}

export interface PaginatedReviews {
  total: number;
  page: number;
  page_size: number;
  items: ReviewSummary[];
}

export const fetchRepos = (): Promise<Repo[]> =>
  api.get<Repo[]>("/api/repos").then((r) => r.data);

export const fetchReviews = (
  repoName: string,
  page = 1
): Promise<PaginatedReviews> =>
  api
    .get<PaginatedReviews>(`/api/repos/${repoName}/reviews`, {
      params: { page },
    })
    .then((r) => r.data);

export const fetchMetrics = (repoName: string): Promise<Metrics> =>
  api
    .get<Metrics>(`/api/repos/${repoName}/metrics`)
    .then((r) => r.data);

export const fetchReview = (reviewId: number): Promise<ReviewDetail> =>
  api.get<ReviewDetail>(`/api/reviews/${reviewId}`).then((r) => r.data);
