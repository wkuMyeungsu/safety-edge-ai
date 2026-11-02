// 웹이 접속할 Supabase 프로젝트.
// Supabase 대시보드 → Project Settings → API 에서 Project URL과 anon(public) key를 넣는다.
// anon key는 브라우저에 공개되는 값이라 커밋해도 된다 (RLS로 읽기만 허용).
// service key는 절대 넣지 않는다.
//
// 두 값이 비어 있으면 페이지는 가짜 데이터로 도는 데모 모드로 열린다.
window.SAFETY_CONFIG = {
  supabaseUrl: "https://sqrvaytfuytjchdmlbvu.supabase.co",
  supabaseAnonKey: "sb_publishable_w4SdI632QqMAXnm4CtcGiQ_BdTUg1OM",
  table: "safety_logs",
  pageSize: 50,
};
