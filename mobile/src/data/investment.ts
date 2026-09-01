export type InvestmentOption = { id:string; label:string; scores:Record<string,number> };
export type InvestmentQuestion = { id:number; primaryAxis:string; title:string; options:InvestmentOption[] };

export const investmentQuestions: InvestmentQuestion[] = [
  {
    "id": 1,
    "primaryAxis": "horizon",
    "title": "산 회사의 매출과 이익은 예상대로 좋아지고 있지만 주가는 4개월째 거의 움직이지 않습니다. 가장 가까운 행동은?",
    "options": [
      {
        "id": "1a",
        "label": "회사가 계속 좋아지고 있다면 주가는 늦게 오를 수도 있으니 계속 가지고 있는다.",
        "scores": {
          "L": 3,
          "H": 1
        }
      },
      {
        "id": "1b",
        "label": "한두 달 더 지켜보면서 다른 좋은 회사와 비교해 투자금 일부를 옮길지 생각한다.",
        "scores": {
          "N": 3,
          "M": 1
        }
      },
      {
        "id": "1c",
        "label": "주가가 너무 오래 움직이지 않으면 최근 흐름이 좋은 다른 회사로 투자금 일부를 옮긴다.",
        "scores": {
          "S": 3,
          "P": 1
        }
      },
      {
        "id": "1d",
        "label": "회사의 매출과 이익, 현재 가격을 다시 보고 더 좋아 보이면 오히려 더 산다.",
        "scores": {
          "L": 2,
          "A": 1,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 2,
    "primaryAxis": "risk",
    "title": "관심 있는 주식이 하루에도 7~8%씩 크게 오르내리지만 앞으로 회사가 크게 성장할 가능성이 높아 보입니다. 어떻게 하시겠습니까?",
    "options": [
      {
        "id": "2a",
        "label": "가격이 너무 크게 오르내리면 좋은 회사라도 투자하지 않는다.",
        "scores": {
          "D": 3,
          "V": 1
        }
      },
      {
        "id": "2b",
        "label": "아주 적은 금액으로 먼저 사보고 가격 움직임이 안정되면 더 산다.",
        "scores": {
          "D": 2,
          "N": 1,
          "M": 1
        }
      },
      {
        "id": "2c",
        "label": "충분히 알아본 뒤 괜찮다고 생각되면 다른 주식과 비슷한 금액을 투자한다.",
        "scores": {
          "A": 2,
          "G": 1
        }
      },
      {
        "id": "2d",
        "label": "손실 가능성이 커도 크게 오를 가능성이 높다고 판단되면 적극적으로 투자한다.",
        "scores": {
          "A": 3,
          "G": 1,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 3,
    "primaryAxis": "value",
    "title": "두 기업 중 하나만 고른다면 어느 쪽에 더 관심이 갑니까?",
    "options": [
      {
        "id": "3a",
        "label": "지금은 이익이 적지만 앞으로 이 회사가 속한 시장이 크게 커질 가능성이 높은 회사.",
        "scores": {
          "G": 3,
          "L": 1,
          "H": 1
        }
      },
      {
        "id": "3b",
        "label": "빠르게 성장하지는 않지만 회사가 버는 돈과 가진 재산에 비해 주식 가격이 싸 보이는 회사.",
        "scores": {
          "V": 3,
          "D": 1
        }
      },
      {
        "id": "3c",
        "label": "성장 가능성도 괜찮고 주식 가격도 크게 비싸 보이지 않는 안정적인 회사.",
        "scores": {
          "G": 1,
          "V": 1,
          "N": 2,
          "M": 1
        }
      },
      {
        "id": "3d",
        "label": "최근 주가가 더 잘 오르고 사람들의 관심을 많이 받는 회사를 먼저 선택한다.",
        "scores": {
          "S": 2,
          "A": 1,
          "P": 1
        }
      }
    ]
  },
  {
    "id": 4,
    "primaryAxis": "profit",
    "title": "산 주식이 예상보다 빠르게 18% 올랐습니다. 처음 이 회사를 산 이유는 아직 그대로입니다.",
    "options": [
      {
        "id": "4a",
        "label": "수익을 지키기 위해 대부분 정리한다.",
        "scores": {
          "P": 3,
          "D": 1,
          "S": 1
        }
      },
      {
        "id": "4b",
        "label": "절반 정도 팔아서 수익을 챙기고 나머지는 계속 가지고 있는다.",
        "scores": {
          "P": 2,
          "N": 2,
          "M": 1
        }
      },
      {
        "id": "4c",
        "label": "처음 이 회사를 산 이유가 그대로라면 계속 가지고 있는다.",
        "scores": {
          "H": 3,
          "L": 1
        }
      },
      {
        "id": "4d",
        "label": "회사가 더 좋아졌다고 생각되면 이미 올랐어도 조금 더 사는 것을 생각한다.",
        "scores": {
          "H": 2,
          "A": 2,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 5,
    "primaryAxis": "spread",
    "title": "투자할 수 있는 돈이 1,000만원이고 정말 좋아 보이는 주식 하나를 발견했습니다. 이 주식에 얼마 정도 투자하시겠습니까?",
    "options": [
      {
        "id": "5a",
        "label": "100만원 정도만 사고 나머지 돈은 여러 주식에 나눠 투자한다.",
        "scores": {
          "M": 3,
          "D": 1
        }
      },
      {
        "id": "5b",
        "label": "200~250만원 정도 투자하고 나머지는 다른 주식에도 나눠 넣는다.",
        "scores": {
          "M": 2,
          "N": 2
        }
      },
      {
        "id": "5c",
        "label": "좋다고 생각하면 350~400만원 정도까지 투자할 수 있다.",
        "scores": {
          "F": 2,
          "A": 1
        }
      },
      {
        "id": "5d",
        "label": "정말 자신 있다면 500만원 이상도 한 주식에 투자할 수 있다.",
        "scores": {
          "F": 3,
          "A": 2,
          "H": 1
        }
      }
    ]
  },
  {
    "id": 6,
    "primaryAxis": "horizon",
    "title": "새로운 투자 아이디어를 찾을 때 가장 먼저 확인하고 싶은 것은?",
    "options": [
      {
        "id": "6a",
        "label": "3~5년 뒤에도 이 회사가 계속 돈을 잘 벌 수 있을지.",
        "scores": {
          "L": 3,
          "G": 1
        }
      },
      {
        "id": "6b",
        "label": "앞으로 몇 달 동안 매출과 이익이 좋아질지, 지금 가격이 너무 비싸지는 않은지.",
        "scores": {
          "N": 3,
          "V": 1
        }
      },
      {
        "id": "6c",
        "label": "최근 사람들이 많이 사고 있는지, 곧 주가가 오를 만한 좋은 소식이 있는지.",
        "scores": {
          "S": 3,
          "A": 1
        }
      },
      {
        "id": "6d",
        "label": "오랫동안 성장할 회사인지도 보고, 지금 사기 좋은 가격인지도 함께 본다.",
        "scores": {
          "L": 1,
          "N": 2,
          "G": 1
        }
      }
    ]
  },
  {
    "id": 7,
    "primaryAxis": "risk",
    "title": "좋다고 생각해 산 주식이 12% 떨어졌지만 회사의 매출과 이익은 아직 나빠지지 않았습니다.",
    "options": [
      {
        "id": "7a",
        "label": "더 떨어질까 걱정되어 일부 또는 전부 판다.",
        "scores": {
          "D": 3,
          "P": 1
        }
      },
      {
        "id": "7b",
        "label": "당장은 사고팔지 않고 왜 떨어졌는지 더 알아본다.",
        "scores": {
          "D": 1,
          "N": 2
        }
      },
      {
        "id": "7c",
        "label": "처음 좋게 본 이유가 그대로라면 지금 가격에서 조금 더 산다.",
        "scores": {
          "A": 2,
          "L": 1
        }
      },
      {
        "id": "7d",
        "label": "회사의 상태가 그대로 좋다면 싸게 살 기회라고 보고 적극적으로 더 산다.",
        "scores": {
          "A": 3,
          "V": 1,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 8,
    "primaryAxis": "value",
    "title": "비슷한 회사들보다 주식 가격이 비싼 편이지만 매출이 매년 30%씩 빠르게 늘고 있는 회사입니다.",
    "options": [
      {
        "id": "8a",
        "label": "회사가 잘 성장해도 지금 가격은 너무 비싸 보이므로 기다린다.",
        "scores": {
          "V": 3,
          "D": 1
        }
      },
      {
        "id": "8b",
        "label": "가격이 조금 내려오면 살 수 있도록 계속 지켜본다.",
        "scores": {
          "V": 2,
          "N": 1
        }
      },
      {
        "id": "8c",
        "label": "앞으로도 오랫동안 빠르게 성장할 이유가 충분하다면 지금 가격에도 살 수 있다.",
        "scores": {
          "G": 3,
          "L": 1
        }
      },
      {
        "id": "8d",
        "label": "회사도 빠르게 성장하고 최근 주가도 계속 오르는 흐름이라면 적극적으로 산다.",
        "scores": {
          "G": 2,
          "A": 2,
          "S": 1
        }
      }
    ]
  },
  {
    "id": 9,
    "primaryAxis": "profit",
    "title": "수익 중인 주식이 최근 가장 높았던 가격에서 6% 내려왔지만 전체적으로는 아직 오르는 흐름입니다.",
    "options": [
      {
        "id": "9a",
        "label": "수익이 더 줄기 전에 정리한다.",
        "scores": {
          "P": 3,
          "D": 1
        }
      },
      {
        "id": "9b",
        "label": "일부만 팔아 수익을 확보한다.",
        "scores": {
          "P": 2,
          "M": 1,
          "N": 1
        }
      },
      {
        "id": "9c",
        "label": "주가가 계속 오르는 흐름이 확실히 끝날 때까지 가지고 있는다.",
        "scores": {
          "H": 3,
          "S": 1
        }
      },
      {
        "id": "9d",
        "label": "회사가 얼마나 좋은지가 더 중요하므로 최근에 조금 떨어진 것은 크게 신경 쓰지 않는다.",
        "scores": {
          "H": 2,
          "L": 2
        }
      }
    ]
  },
  {
    "id": 10,
    "primaryAxis": "spread",
    "title": "같은 업종에서 앞으로 잘될 것 같은 회사가 4개 보입니다. 가장 자연스러운 선택은?",
    "options": [
      {
        "id": "10a",
        "label": "가장 좋은 한 기업만 깊게 분석해 투자한다.",
        "scores": {
          "F": 3
        }
      },
      {
        "id": "10b",
        "label": "상위 두 기업에 대부분을 나눠 투자한다.",
        "scores": {
          "F": 2,
          "M": 1
        }
      },
      {
        "id": "10c",
        "label": "3~4개 회사에 비슷한 금액을 나눠 투자한다.",
        "scores": {
          "M": 3
        }
      },
      {
        "id": "10d",
        "label": "이 업종뿐 아니라 다른 업종의 주식도 함께 사서 위험을 더 나눈다.",
        "scores": {
          "M": 3,
          "D": 1
        }
      }
    ]
  },
  {
    "id": 11,
    "primaryAxis": "risk",
    "title": "회사가 곧 매출과 이익을 발표할 예정이고, 현재 이 주식에서 5% 수익이 나고 있습니다.",
    "options": [
      {
        "id": "11a",
        "label": "발표 결과가 나쁠 수도 있으니 발표 전에 대부분 판다.",
        "scores": {
          "D": 3,
          "P": 2
        }
      },
      {
        "id": "11b",
        "label": "일부만 팔아 발표 결과가 나쁠 때 손실을 줄인다.",
        "scores": {
          "D": 2,
          "M": 1
        }
      },
      {
        "id": "11c",
        "label": "회사가 잘하고 있다고 생각하면 팔지 않고 발표 결과를 확인한다.",
        "scores": {
          "A": 2,
          "H": 1
        }
      },
      {
        "id": "11d",
        "label": "매출과 이익이 크게 좋아질 것이라고 확신하면 발표 전에 더 살 수도 있다.",
        "scores": {
          "A": 3,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 12,
    "primaryAxis": "horizon",
    "title": "종목을 매수한 뒤 어떤 주기로 확인하는 편이 가장 마음에 가깝습니까?",
    "options": [
      {
        "id": "12a",
        "label": "회사의 매출과 이익 발표나 큰 변화가 있을 때 주로 확인한다.",
        "scores": {
          "L": 3
        }
      },
      {
        "id": "12b",
        "label": "일주일에 한두 번 정도 주가와 중요한 뉴스를 확인한다.",
        "scores": {
          "N": 3
        }
      },
      {
        "id": "12c",
        "label": "거의 매일 주가가 얼마나 움직였고 사람들이 얼마나 사고팔았는지 확인한다.",
        "scores": {
          "S": 2,
          "P": 1
        }
      },
      {
        "id": "12d",
        "label": "주식시장이 열려 있는 동안에도 여러 번 가격을 확인한다.",
        "scores": {
          "S": 3,
          "A": 1
        }
      }
    ]
  },
  {
    "id": 13,
    "primaryAxis": "value",
    "title": "최근 1년간 주가는 거의 오르지 않았지만 회사가 꾸준히 돈을 벌고 있고 주주에게 나눠주는 돈도 늘고 있는 회사입니다.",
    "options": [
      {
        "id": "13a",
        "label": "빠르게 성장하지 않아도 주식 가격이 충분히 싸다면 좋은 투자 후보라고 본다.",
        "scores": {
          "V": 3,
          "D": 1,
          "L": 1
        }
      },
      {
        "id": "13b",
        "label": "내가 가진 주식들 중 안정적인 한 종목으로는 괜찮다고 본다.",
        "scores": {
          "V": 2,
          "M": 1
        }
      },
      {
        "id": "13c",
        "label": "성장성이 부족하다면 큰 매력은 느끼지 못한다.",
        "scores": {
          "G": 2,
          "A": 1
        }
      },
      {
        "id": "13d",
        "label": "최근 주가가 거의 오르지 않는다면 다른 주식을 먼저 찾는다.",
        "scores": {
          "S": 2,
          "P": 1
        }
      }
    ]
  },
  {
    "id": 14,
    "primaryAxis": "profit",
    "title": "매수할 때 목표 수익률을 정하는 방식은?",
    "options": [
      {
        "id": "14a",
        "label": "10~15%처럼 명확한 숫자를 정하고 도달하면 정리한다.",
        "scores": {
          "P": 3,
          "S": 1
        }
      },
      {
        "id": "14b",
        "label": "목표로 생각한 수익 범위는 있지만 상황에 따라 파는 시점을 바꾼다.",
        "scores": {
          "P": 2,
          "N": 2
        }
      },
      {
        "id": "14c",
        "label": "정해진 수익률보다 주가가 더 이상 오르지 않는 흐름으로 바뀌는지를 본다.",
        "scores": {
          "H": 2,
          "S": 1
        }
      },
      {
        "id": "14d",
        "label": "회사의 장기적인 성장 가능성이 나빠질 때까지 특별히 얼마에 팔겠다는 가격을 정하지 않는다.",
        "scores": {
          "H": 3,
          "L": 2
        }
      }
    ]
  },
  {
    "id": 15,
    "primaryAxis": "spread",
    "title": "한 주식이 많이 올라 내가 투자한 전체 돈의 40%를 차지하게 됐습니다. 회사의 전망은 여전히 좋습니다.",
    "options": [
      {
        "id": "15a",
        "label": "한 주식에 너무 많은 돈이 몰렸으므로 일부 팔아 원래 생각했던 투자금 수준으로 줄인다.",
        "scores": {
          "M": 3,
          "D": 1,
          "P": 1
        }
      },
      {
        "id": "15b",
        "label": "조금만 팔아 위험을 낮추되 여전히 가장 많이 투자한 주식으로 유지한다.",
        "scores": {
          "M": 2,
          "F": 1
        }
      },
      {
        "id": "15c",
        "label": "가장 자신 있는 주식이라면 전체 투자금의 40%가 되어도 괜찮다.",
        "scores": {
          "F": 3,
          "H": 1
        }
      },
      {
        "id": "15d",
        "label": "회사가 더 좋아졌다고 생각한다면 한 주식에 많은 돈이 들어가 있는 것 자체는 문제라고 생각하지 않는다.",
        "scores": {
          "F": 3,
          "A": 1
        }
      }
    ]
  },
  {
    "id": 16,
    "primaryAxis": "horizon",
    "title": "산 주식이 예상했던 좋은 소식 때문에 일주일 만에 크게 올랐습니다. 이후에는 어떻게 하시겠습니까?",
    "options": [
      {
        "id": "16a",
        "label": "기대했던 좋은 소식이 이미 주가에 반영됐다고 보고 빠르게 팔아 수익을 챙긴다.",
        "scores": {
          "S": 3,
          "P": 2
        }
      },
      {
        "id": "16b",
        "label": "일부만 팔아 수익을 챙기고 나머지는 주가 움직임을 더 지켜본다.",
        "scores": {
          "N": 2,
          "P": 1
        }
      },
      {
        "id": "16c",
        "label": "며칠 사이 크게 오른 것보다 앞으로 회사의 매출과 이익이 더 좋아질지를 보고 결정한다.",
        "scores": {
          "N": 2,
          "L": 1
        }
      },
      {
        "id": "16d",
        "label": "오랫동안 성장할 회사라는 생각이 그대로라면 갑자기 많이 올라도 계속 가지고 있는다.",
        "scores": {
          "L": 3,
          "H": 1
        }
      }
    ]
  },
  {
    "id": 17,
    "primaryAxis": "risk",
    "title": "투자할 수 있는 돈 중 35%를 아직 현금으로 가지고 있는데 주식시장이 계속 크게 오르고 있습니다.",
    "options": [
      {
        "id": "17a",
        "label": "이미 많이 오른 주식을 따라 사지 않고 현금을 가지고 가격이 내려오기를 기다린다.",
        "scores": {
          "D": 3,
          "V": 1
        }
      },
      {
        "id": "17b",
        "label": "좋아 보이는 주식만 조금씩 사면서 현금을 천천히 투자한다.",
        "scores": {
          "D": 1,
          "N": 2
        }
      },
      {
        "id": "17c",
        "label": "주식시장이 계속 오르는 흐름이라고 생각되면 현금으로 남겨둔 돈을 적극적으로 투자한다.",
        "scores": {
          "A": 2,
          "S": 1
        }
      },
      {
        "id": "17d",
        "label": "더 오를 기회를 놓치는 것이 더 아쉬워 남은 현금 대부분을 투자할 수 있다.",
        "scores": {
          "A": 3,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 18,
    "primaryAxis": "value",
    "title": "어떤 회사를 살지 알아볼 때 가장 먼저 궁금한 것은 무엇입니까?",
    "options": [
      {
        "id": "18a",
        "label": "회사의 매출이 얼마나 빠르게 늘고 있는지, 앞으로 시장이 얼마나 커질지, 새로운 사업이 있는지.",
        "scores": {
          "G": 3
        }
      },
      {
        "id": "18b",
        "label": "회사가 버는 돈과 가진 재산에 비해 지금 주식 가격이 싼지 비싼지.",
        "scores": {
          "V": 3
        }
      },
      {
        "id": "18c",
        "label": "회사가 가진 돈을 잘 활용해 꾸준히 이익을 내고 있는지.",
        "scores": {
          "G": 1,
          "V": 1,
          "L": 1
        }
      },
      {
        "id": "18d",
        "label": "최근 주가가 얼마나 올랐는지, 사람들이 많이 사고 있는지, 주가 움직임이 어떤지.",
        "scores": {
          "S": 3,
          "A": 1
        }
      }
    ]
  },
  {
    "id": 19,
    "primaryAxis": "profit",
    "title": "산 주식이 하루 만에 12% 크게 올라 예상보다 큰 수익이 생겼습니다.",
    "options": [
      {
        "id": "19a",
        "label": "갑작스러운 수익은 바로 대부분 확정한다.",
        "scores": {
          "P": 3,
          "D": 1
        }
      },
      {
        "id": "19b",
        "label": "일부를 팔아 처음 투자한 돈의 일부를 돌려받고 나머지는 계속 가지고 있는다.",
        "scores": {
          "P": 2,
          "M": 1
        }
      },
      {
        "id": "19c",
        "label": "사려는 사람이 많고 계속 오르는 흐름이면 더 오를 수 있다고 기대한다.",
        "scores": {
          "H": 2,
          "S": 2,
          "A": 1
        }
      },
      {
        "id": "19d",
        "label": "하루 동안 크게 오른 것보다 처음에 이 회사를 오래 가지고 있으려 했던 이유를 더 중요하게 본다.",
        "scores": {
          "H": 3,
          "L": 2
        }
      }
    ]
  },
  {
    "id": 20,
    "primaryAxis": "spread",
    "title": "새로 좋아 보이는 주식을 발견했지만 이미 8개의 주식을 가지고 있습니다.",
    "options": [
      {
        "id": "20a",
        "label": "기존 주식 중 덜 좋아 보이는 것을 팔고 새 주식에 더 많이 투자한다.",
        "scores": {
          "F": 3
        }
      },
      {
        "id": "20b",
        "label": "기존 주식에 들어간 돈을 조금씩 줄여 새 주식에도 충분한 금액을 투자한다.",
        "scores": {
          "F": 1,
          "M": 2
        }
      },
      {
        "id": "20c",
        "label": "새 주식에는 적은 금액만 투자해 여러 주식으로 나눠 가진 상태를 유지한다.",
        "scores": {
          "M": 3
        }
      },
      {
        "id": "20d",
        "label": "이미 가진 주식이 많으므로 새 주식은 사지 않는다.",
        "scores": {
          "M": 2,
          "D": 1
        }
      }
    ]
  },
  {
    "id": 21,
    "primaryAxis": "risk",
    "title": "아직 회사가 이익을 내지는 못하고 있지만 기술력이 좋고 많은 사람들이 관심을 갖는 회사입니다.",
    "options": [
      {
        "id": "21a",
        "label": "회사가 실제로 돈을 벌기 시작하기 전에는 투자하지 않는다.",
        "scores": {
          "D": 3,
          "V": 2
        }
      },
      {
        "id": "21b",
        "label": "회사를 지켜본다는 생각으로 아주 적은 금액만 투자할 수 있다.",
        "scores": {
          "D": 1,
          "G": 1,
          "M": 1
        }
      },
      {
        "id": "21c",
        "label": "앞으로 크게 성장할 가능성이 충분하다면 다른 주식과 비슷한 금액을 투자한다.",
        "scores": {
          "A": 2,
          "G": 2
        }
      },
      {
        "id": "21d",
        "label": "성공했을 때 크게 오를 수 있다면 손실 위험이 높아도 투자할 수 있다.",
        "scores": {
          "A": 3,
          "G": 2,
          "H": 1
        }
      }
    ]
  },
  {
    "id": 22,
    "primaryAxis": "horizon",
    "title": "내가 주식을 잘 선택했는지 판단하려면 어느 정도 기간을 보는 것이 가장 자연스럽습니까?",
    "options": [
      {
        "id": "22a",
        "label": "최소 1~3년은 지나야 제대로 평가할 수 있다.",
        "scores": {
          "L": 3
        }
      },
      {
        "id": "22b",
        "label": "6개월~1년 정도면 내가 고른 주식이 괜찮았는지 판단할 수 있다.",
        "scores": {
          "N": 3
        }
      },
      {
        "id": "22c",
        "label": "한두 달 안에도 생각과 다르게 움직이면 다른 주식으로 바꿀 수 있다.",
        "scores": {
          "S": 2,
          "N": 1
        }
      },
      {
        "id": "22d",
        "label": "며칠~몇 주 안에 기대했던 움직임이 나오지 않으면 다른 주식을 찾는다.",
        "scores": {
          "S": 3
        }
      }
    ]
  },
  {
    "id": 23,
    "primaryAxis": "value",
    "title": "주가가 이미 많이 올랐지만 앞으로 회사의 매출과 이익도 계속 좋아질 것으로 예상되는 회사를 발견했습니다.",
    "options": [
      {
        "id": "23a",
        "label": "이미 너무 많이 오른 것 같아 지금은 사지 않고 기다린다.",
        "scores": {
          "V": 3,
          "D": 1
        }
      },
      {
        "id": "23b",
        "label": "가격이 조금 내려올 때까지 사지 않고 계속 지켜본다.",
        "scores": {
          "V": 2,
          "N": 1
        }
      },
      {
        "id": "23c",
        "label": "주가가 오른 것보다 회사가 더 빠르게 좋아지고 있다면 지금도 살 수 있다.",
        "scores": {
          "G": 3
        }
      },
      {
        "id": "23d",
        "label": "회사의 매출과 이익도 좋아지고 주가도 계속 오르고 있다면 적극적으로 살 수 있다.",
        "scores": {
          "G": 2,
          "S": 2,
          "A": 1
        }
      }
    ]
  },
  {
    "id": 24,
    "primaryAxis": "profit",
    "title": "한 주식에서 이미 40% 수익이 났는데, 처음 기대했던 회사의 좋은 변화가 이제 막 실제로 나타나기 시작했습니다.",
    "options": [
      {
        "id": "24a",
        "label": "40%면 충분한 수익이므로 대부분 정리한다.",
        "scores": {
          "P": 3,
          "D": 1
        }
      },
      {
        "id": "24b",
        "label": "절반 정도만 수익을 확정한다.",
        "scores": {
          "P": 2,
          "M": 1
        }
      },
      {
        "id": "24c",
        "label": "회사가 이제 본격적으로 좋아지기 시작했다면 더 큰 수익을 기다린다.",
        "scores": {
          "H": 3,
          "G": 1
        }
      },
      {
        "id": "24d",
        "label": "회사가 앞으로 오랫동안 성장하기 시작한 단계라고 생각되면 몇 년 더 가지고 있을 수 있다.",
        "scores": {
          "H": 3,
          "L": 2
        }
      }
    ]
  },
  {
    "id": 25,
    "primaryAxis": "spread",
    "title": "내가 가장 편하게 관리할 수 있는 주식 보유 방식은 어느 쪽에 가깝습니까?",
    "options": [
      {
        "id": "25a",
        "label": "3~5개의 주식만 골라 자세히 살펴보며 투자한다.",
        "scores": {
          "F": 3
        }
      },
      {
        "id": "25b",
        "label": "6~10개 정도의 주식을 중심으로 관리한다.",
        "scores": {
          "F": 1,
          "M": 2
        }
      },
      {
        "id": "25c",
        "label": "10~15개 이상의 주식을 여러 업종으로 나눠 가진다.",
        "scores": {
          "M": 3
        }
      },
      {
        "id": "25d",
        "label": "한두 주식에 몰기보다 여러 종류의 주식과 투자상품에 최대한 넓게 나눠 두는 것이 편하다.",
        "scores": {
          "M": 3,
          "D": 1
        }
      }
    ]
  },
  {
    "id": 26,
    "primaryAxis": "risk",
    "title": "주식시장 전체가 갑자기 10% 이상 크게 떨어졌습니다. 관심 있던 회사들의 매출과 이익 전망에는 큰 변화가 없습니다.",
    "options": [
      {
        "id": "26a",
        "label": "더 떨어질까 걱정되어 가지고 있던 주식을 일부 팔고 현금을 늘린다.",
        "scores": {
          "D": 3,
          "P": 1
        }
      },
      {
        "id": "26b",
        "label": "가지고 있는 주식은 팔지 않지만 당분간 새로 사지도 않는다.",
        "scores": {
          "D": 2,
          "N": 1
        }
      },
      {
        "id": "26c",
        "label": "좋게 봤던 회사의 주식을 한 번에 많이 사지 않고 조금씩 나눠 산다.",
        "scores": {
          "A": 2,
          "V": 1,
          "M": 1
        }
      },
      {
        "id": "26d",
        "label": "평소 사고 싶었던 가격까지 내려왔다면 적극적으로 더 산다.",
        "scores": {
          "A": 3,
          "V": 1,
          "F": 1
        }
      }
    ]
  },
  {
    "id": 27,
    "primaryAxis": "horizon",
    "title": "회사의 먼 미래 전망은 좋지만 앞으로 2~3개월 동안은 특별히 매출이나 이익이 좋아질 만한 일이 없어 보입니다.",
    "options": [
      {
        "id": "27a",
        "label": "앞으로 몇 년 뒤의 모습이 더 중요하므로 계속 가지고 있는다.",
        "scores": {
          "L": 3
        }
      },
      {
        "id": "27b",
        "label": "지금 투자한 금액은 그대로 두고 다음 매출과 이익 발표를 확인한다.",
        "scores": {
          "N": 2,
          "L": 1
        }
      },
      {
        "id": "27c",
        "label": "일부를 팔아 그 돈으로 가까운 시기에 더 오를 것 같은 다른 주식을 찾아본다.",
        "scores": {
          "S": 2,
          "N": 1
        }
      },
      {
        "id": "27d",
        "label": "당분간 주가가 오를 만한 특별한 소식이 없다면 팔고 나중에 다시 본다.",
        "scores": {
          "S": 3,
          "P": 1
        }
      }
    ]
  },
  {
    "id": 28,
    "primaryAxis": "value",
    "title": "빠르게 성장하지는 않지만 업계 1위이고 꾸준히 이익을 잘 내며 회사가 가진 현금도 많은 회사입니다.",
    "options": [
      {
        "id": "28a",
        "label": "주식 가격까지 싸 보인다면 매우 매력적이라고 느낀다.",
        "scores": {
          "V": 3,
          "L": 1
        }
      },
      {
        "id": "28b",
        "label": "안정적으로 오래 가지고 갈 주식으로 일부 투자할 수 있다.",
        "scores": {
          "V": 2,
          "D": 1,
          "M": 1
        }
      },
      {
        "id": "28c",
        "label": "좋은 회사여도 앞으로 빠르게 성장할 가능성이 낮다면 많은 돈을 투자하기는 어렵다.",
        "scores": {
          "G": 2
        }
      },
      {
        "id": "28d",
        "label": "사람들의 관심이 적고 최근 주가도 잘 오르지 않는다면 우선순위가 낮다.",
        "scores": {
          "S": 2,
          "A": 1
        }
      }
    ]
  },
  {
    "id": 29,
    "primaryAxis": "profit",
    "title": "수익 중인 주식에 좋지 않은 뉴스가 나왔지만 회사는 잠깐 생긴 문제라고 설명했습니다.",
    "options": [
      {
        "id": "29a",
        "label": "아직 수익이 남아 있을 때 먼저 팔아 손실 위험을 없앤다.",
        "scores": {
          "P": 3,
          "D": 2
        }
      },
      {
        "id": "29b",
        "label": "일부만 팔고 실제로 얼마나 심각한 문제인지 더 확인한다.",
        "scores": {
          "P": 1,
          "D": 1,
          "N": 2
        }
      },
      {
        "id": "29c",
        "label": "회사의 중요한 사업이 나빠진 것이 아니라면 그대로 가지고 있는다.",
        "scores": {
          "H": 2,
          "L": 1
        }
      },
      {
        "id": "29d",
        "label": "사람들이 뉴스에 너무 크게 반응했다고 생각되면 오히려 더 사는 것도 생각한다.",
        "scores": {
          "H": 1,
          "A": 3,
          "V": 1
        }
      }
    ]
  },
  {
    "id": 30,
    "primaryAxis": "spread",
    "title": "올해 가장 좋아 보이는 주식 하나를 발견했습니다. 이미 가지고 있는 다른 주식들과 비교하면 어떻게 투자하시겠습니까?",
    "options": [
      {
        "id": "30a",
        "label": "아무리 좋아 보여도 다른 주식과 비슷한 금액만 투자한다.",
        "scores": {
          "M": 3,
          "D": 1
        }
      },
      {
        "id": "30b",
        "label": "다른 주식보다 조금 더 많은 금액을 투자한다.",
        "scores": {
          "M": 1,
          "F": 2
        }
      },
      {
        "id": "30c",
        "label": "다른 주식보다 훨씬 좋아 보인다면 기존 주식을 일부 팔고 이 주식에 더 많은 돈을 투자한다.",
        "scores": {
          "F": 3,
          "A": 1
        }
      },
      {
        "id": "30d",
        "label": "가장 좋아 보이는 한 주식에 많은 돈을 투자하는 것이 더 합리적이라고 생각한다.",
        "scores": {
          "F": 3,
          "A": 2,
          "H": 1
        }
      }
    ]
  }
] as InvestmentQuestion[];

export const investmentTraits: Record<string,{name:string;short:string;summary:string;strength:string;caution:string}> = {
  L:{name:'장기투자형',short:'장기',summary:'시간과 복리, 기업의 장기 성장 스토리를 믿고 기다리는 편입니다.',strength:'시장 소음에 흔들리지 않고 좋은 기업의 성장을 오래 가져갈 수 있습니다.',caution:'투자 논리가 훼손됐는데도 단순히 오래 보유하는 실수를 경계해야 합니다.'},
  N:{name:'신중 관망형',short:'균형',summary:'기간을 고정하기보다 상황과 투자 논리에 맞춰 유연하게 대응합니다.',strength:'장기와 단기의 장점을 섞어 시장 변화에 비교적 유연하게 대응합니다.',caution:'판단 기준이 모호하면 매도/보유 결정을 계속 미룰 수 있습니다.'},
  S:{name:'단기투자형',short:'단기',summary:'짧은 기간의 가격 변화와 타이밍을 적극적으로 활용하는 편입니다.',strength:'시장 변화에 빠르게 대응하고 기회비용을 민감하게 관리합니다.',caution:'잦은 매매와 단기 노이즈에 과도하게 반응하지 않도록 기준이 필요합니다.'},
  A:{name:'공격적 투자형',short:'공격',summary:'수익 기회가 크다고 판단하면 변동성을 감수하고 적극적으로 투자합니다.',strength:'확신이 높은 기회에서 높은 수익 잠재력을 적극적으로 활용합니다.',caution:'손실 폭과 포지션 크기를 미리 정하지 않으면 낙폭도 커질 수 있습니다.'},
  D:{name:'방어적 투자형',short:'방어',summary:'수익률보다 먼저 손실 가능성과 자산 보전을 확인하는 편입니다.',strength:'하락장에서 계좌를 지키고 감정적인 큰 손실을 줄이는 데 유리합니다.',caution:'위험을 너무 피하면 좋은 상승 기회를 충분히 활용하지 못할 수 있습니다.'},
  G:{name:'미래가치형',short:'성장',summary:'현재 숫자보다 앞으로 커질 시장과 기업의 성장 가능성을 중요하게 봅니다.',strength:'산업 구조 변화와 장기 성장 기업을 일찍 발견하는 데 강점이 있습니다.',caution:'좋은 미래 이야기만으로 지나치게 높은 가격을 정당화하지 않도록 주의해야 합니다.'},
  V:{name:'현실가치형',short:'가치',summary:'현재 실적과 자산, 밸류에이션처럼 확인 가능한 숫자를 더 중요하게 봅니다.',strength:'가격 대비 실제 가치와 안전마진을 꼼꼼하게 확인하는 데 강점이 있습니다.',caution:'싸다는 이유만으로 성장성이 약한 기업을 오래 보유하는 가치 함정을 조심해야 합니다.'},
  P:{name:'빠른수익실현형',short:'빠른실현',summary:'목표 수익이 어느 정도 나면 확보한 이익을 빠르게 확정하는 편입니다.',strength:'수익을 실제 계좌 이익으로 확정하고 급격한 되돌림 위험을 줄입니다.',caution:'좋은 종목의 큰 추세가 시작됐는데 너무 빨리 내려 수익을 제한할 수 있습니다.'},
  H:{name:'큰수익추구형',short:'큰수익',summary:'투자 논리가 유지되는 동안 큰 수익 구간을 기다리는 편입니다.',strength:'강한 추세와 장기 승자를 오래 보유해 큰 수익을 노릴 수 있습니다.',caution:'이미 큰 수익이 난 뒤에도 욕심 때문에 이익을 상당 부분 반납할 수 있습니다.'},
  F:{name:'집중투자형',short:'집중',summary:'확신이 높은 소수 종목에 자금을 집중하는 편입니다.',strength:'분석이 맞았을 때 좋은 아이디어의 수익 기여도를 크게 만들 수 있습니다.',caution:'한 종목/한 산업의 예상치 못한 악재가 계좌 전체에 큰 영향을 줄 수 있습니다.'},
  M:{name:'분산투자형',short:'분산',summary:'여러 종목과 업종으로 나눠 특정 종목의 위험을 줄이는 편입니다.',strength:'개별 종목 실수가 전체 계좌에 미치는 충격을 줄이는 데 유리합니다.',caution:'종목 수가 지나치게 많아지면 좋은 아이디어의 효과가 희석되고 관리가 어려워질 수 있습니다.'},
};

export const investmentAxes = [
  {key:'horizon',name:'투자 기간',letters:['L','N','S'],caption:'오래 보유 ↔ 상황 대응 ↔ 빠른 기회 포착'},
  {key:'risk',name:'위험 감수',letters:['A','D'],caption:'높은 변동 감수 ↔ 손실 방어 우선'},
  {key:'value',name:'가치 판단',letters:['G','V'],caption:'미래 성장성 ↔ 현재 가격과 가치'},
  {key:'profit',name:'수익 실현',letters:['P','H'],caption:'수익 확보 ↔ 상승 여력 추구'},
  {key:'spread',name:'종목 배분',letters:['F','M'],caption:'소수 종목 집중 ↔ 여러 종목 분산'},
] as const;

export const allInvestmentCodes = ['L','N','S'].flatMap(h=>['A','D'].flatMap(r=>['G','V'].flatMap(v=>['P','H'].flatMap(p=>['F','M'].map(m=>`${h}${r}${v}${p}${m}`)))));

export function profileCodeTitle(code:string){return code.split('').map(x=>investmentTraits[x]?.name||x).join(' · ')}
export function profileNickname(code:string){const parts=code.split('').map(x=>investmentTraits[x]?.short||x);return parts.length===5?`${parts[0]} ${parts[1]} · ${parts[2]} ${parts[3]} · ${parts[4]}`:code}

export function calculateInvestmentProfile(answers: Record<number,string>) {
  const points: Record<string,Record<string,number>> = {
    horizon:{L:0,N:0,S:0}, risk:{A:0,D:0}, value:{G:0,V:0}, profit:{P:0,H:0}, spread:{F:0,M:0},
  };
  const letterAxis: Record<string,string> = {L:'horizon',N:'horizon',S:'horizon',A:'risk',D:'risk',G:'value',V:'value',P:'profit',H:'profit',F:'spread',M:'spread'};
  for (const question of investmentQuestions) {
    const option = question.options.find(x=>x.id===answers[question.id]);
    if (!option) continue;
    Object.entries(option.scores || {}).forEach(([letter,weight])=>{ const axis=letterAxis[letter]; if(axis&&letter in points[axis]) points[axis][letter]+=Number(weight)||0; });
  }
  const percentages: Record<string,Record<string,number>> = {};
  for (const axis of investmentAxes) {
    const values=points[axis.key];
    const total=Object.values(values).reduce((sum,value)=>sum+value,0);
    percentages[axis.key]={};
    axis.letters.forEach(letter=>{ percentages[axis.key][letter]=total?Math.round(values[letter]/total*100):Math.round(100/axis.letters.length); });
  }
  const pickMax=(axis:string,fallback:string)=>{ const entries=Object.entries(points[axis]); const max=Math.max(...entries.map(([,v])=>v)); const winners=entries.filter(([,v])=>v===max).map(([k])=>k); return winners.length===1?winners[0]:(winners.includes(fallback)?fallback:winners[0]); };
  const code=[pickMax('horizon','N'),pickMax('risk','D'),pickMax('value','V'),pickMax('profit','P'),pickMax('spread','M')].join('');
  const serializedAnswers = investmentQuestions.map(q=>({question_id:q.id,axis:q.primaryAxis,value:answers[q.id],option_label:q.options.find(o=>o.id===answers[q.id])?.label||''}));
  return {code, counts:points, percentages, serializedAnswers};
}
