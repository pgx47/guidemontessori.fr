import raw from './books.json';

export interface Book {
  id: string;
  title: string;
  author?: string;
  ageRange?: string;
  description: string;
  amazonUrl: string;
  price: string;
  category?: string;
  level?: string;
  targetAudience: 'child' | 'parent';
  image?: string;
  asin?: string;
}

export const books = raw as Book[];
export const booksFor = (audience: Book['targetAudience']) => books.filter((b) => b.targetAudience === audience);
